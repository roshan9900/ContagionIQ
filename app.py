from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

# Ensure contagioniq root is importable regardless of current working directory
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

from adapters.covenant_guard import CovenantGuardAdapter
from adapters.data_xmine import DataXMineAdapter
from adapters.i360 import I360Adapter
from adapters.model_infinity import ModelInfinityAdapter
from agent_framework import AgentResponseUpdate
from agents.tools import publish_investigation_report
from agents.workflow import build_contagion_workflow
from engine.financials import FinancialStressEngine
from engine.graph import SupplyChainGraphEngine
from observability.audit import InvestigationAuditLogger


DEFAULT_PROMPT = (
    "Coking coal prices increased by 20% due to supply disruption. "
    "Investigate direct and 2-hop downstream contagion across Steel, Auto Components, "
    "Auto OEMs, and Infrastructure."
)
HISTORY_FILE = ROOT_DIR / "data" / "published_analyses.json"


def load_analysis_records(history_path: Path = HISTORY_FILE) -> list[dict[str, Any]]:
    """Loads persisted contagion analysis records from disk (newest first)."""
    if not history_path.exists():
        return []
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return list(raw)
    except (json.JSONDecodeError, OSError):
        return []
    return []


def save_analysis_record(
    record: dict[str, Any],
    history_path: Path = HISTORY_FILE,
) -> dict[str, Any]:
    """Prepends a new analysis record to the persistent JSON store."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    records = load_analysis_records(history_path)
    now = datetime.now()
    enriched = {
        "analysis_id": record.get("analysis_id") or f"AN-{now.strftime('%Y%m%d-%H%M%S-%f')[:19]}",
        "saved_at": record.get("saved_at") or now.strftime("%Y-%m-%d %H:%M:%S"),
        "saved_date": record.get("saved_date") or now.strftime("%Y-%m-%d"),
        **record,
    }
    records.insert(0, enriched)
    history_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return enriched


def filter_analysis_records(
    records: list[dict[str, Any]],
    status_filter: str = "All",
    min_shock_pct: float = 0.0,
    search_query: str = "",
    date_filter: str = "All",
) -> list[dict[str, Any]]:
    """Filters persisted analysis records by status, minimum shock, date, and keyword."""
    query = search_query.strip().lower()
    filtered: list[dict[str, Any]] = []
    for rec in records:
        if status_filter != "All" and rec.get("status") != status_filter:
            continue
        if float(rec.get("shock_pct", 0.0)) < float(min_shock_pct):
            continue
        if date_filter != "All" and rec.get("saved_date") != date_filter:
            continue
        if query:
            haystack = " ".join(
                [
                    str(rec.get("analysis_id", "")),
                    str(rec.get("prompt", "")),
                    str(rec.get("final_report", "")),
                    " ".join(str(c) for c in rec.get("breached_companies", [])),
                ]
            ).lower()
            if query not in haystack:
                continue
        filtered.append(rec)
    return filtered

HOP_COORDS: dict[str, tuple[float, float, int]] = {
    # Hop 0: Upstream Energy & Primary Steel
    "ENERGY_A": (0.0, 3.4, 0),
    "STEEL_A": (0.0, 2.0, 0),
    "STEEL_B": (0.0, 0.4, 0),
    "ENERGY_B": (0.0, -1.2, 0),
    # Hop 1: Auto Components, Cement & Infrastructure
    "AUTO_SUP_A": (2.2, 3.3, 1),
    "AUTO_SUP_B": (2.2, 2.1, 1),
    "AUTO_SUP_C": (2.2, 0.9, 1),
    "INFRA_A": (2.2, -0.2, 1),
    "INFRA_B": (2.2, -1.4, 1),
    "CEMENT_A": (2.2, -2.5, 1),
    "CEMENT_B": (2.2, -3.6, 1),
    # Hop 2: Auto OEMs & Downstream Infrastructure
    "OEM_A": (4.4, 2.9, 2),
    "OEM_B": (4.4, 1.3, 2),
    "INFRA_C": (4.4, -0.8, 2),
}


@st.cache_resource
def get_services(dataset_key: str = "india") -> dict[str, Any]:
    data_dir = ROOT_DIR / "data_india"
    i360 = I360Adapter(data_path=data_dir / "i360.json")
    covenant = CovenantGuardAdapter(data_path=data_dir / "covenant_guard.json")
    xmine = DataXMineAdapter(data_path=data_dir / "data_xmine.json")
    models = ModelInfinityAdapter(data_path=data_dir / "model_infinity.json")
    graph = SupplyChainGraphEngine(xmine.list_edges())
    financial = FinancialStressEngine(raw_material_share_of_cogs=0.55)
    return {
        "i360": i360,
        "covenant": covenant,
        "xmine": xmine,
        "models": models,
        "graph": graph,
        "financial": financial,
        "audit": InvestigationAuditLogger(),
    }


def _get_active_provider_label(llm_config: dict[str, Any] | None = None) -> str:
    cfg = llm_config or {}
    provider = str(cfg.get("provider") or os.getenv("LLM_PROVIDER", "local")).strip().lower()
    if provider == "gemini":
        model = str(cfg.get("model") or os.getenv("GEMINI_MODEL") or os.getenv("gemini_model") or "gemini-3.8-flash").strip()
        return f"LLM: Gemini · {model}"
    if provider == "groq":
        model = str(cfg.get("model") or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")).strip()
        return f"LLM: Groq · {model}"
    model = str(cfg.get("model") or os.getenv("LOCAL_LLM_MODEL", "llama3.1")).strip()
    return f"LLM: Local · {model}"


def _render_llm_sidebar() -> dict[str, Any]:
    """Sidebar configuration allowing runtime LLM provider, model, and API key overrides."""
    default_provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if default_provider not in ("gemini", "groq", "local"):
        default_provider = "gemini"

    provider_defaults = {
        "gemini": (os.getenv("GEMINI_MODEL") or os.getenv("gemini_model") or "gemini-3.1-flash-lite").strip(),
        "groq": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        "local": os.getenv("LOCAL_LLM_MODEL", "llama3.1").strip(),
    }

    with st.sidebar:
        st.header("AI Model Configuration")
        st.caption("Decoupled provider settings. Leave API Key blank to use your `.env` / Secrets value.")
        providers = ["gemini", "groq", "local"]
        selected_provider = st.selectbox(
            "LLM Provider",
            options=providers,
            index=providers.index(default_provider),
            format_func=lambda p: {"gemini": "Google Gemini", "groq": "Groq Cloud", "local": "Local Ollama"}[p],
        )
        selected_model = st.text_input(
            "Model Name",
            value=provider_defaults[selected_provider],
            help="e.g. gemini-3.1-flash-lite, llama-3.3-70b-versatile, or llama3.1",
        )
        api_key_override = st.text_input(
            "API Key (Optional Override)",
            value="",
            type="password",
            placeholder="Using .env key if blank",
        )
        base_url_override = ""
        max_tokens_override: int | None = None
        if selected_provider == "local":
            base_url_override = st.text_input(
                "Ollama Base URL",
                value=os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"),
            )
        elif selected_provider == "groq":
            max_tokens_override = int(
                st.number_input(
                    "Max Completion Tokens",
                    min_value=128,
                    max_value=8192,
                    value=int(os.getenv("GROQ_MAX_TOKENS", "512") or 512),
                    step=128,
                )
            )

    return {
        "provider": selected_provider,
        "model": selected_model.strip() or provider_defaults[selected_provider],
        "api_key": api_key_override.strip() or None,
        "base_url": base_url_override.strip() or None,
        "max_tokens": max_tokens_override,
    }


def _short_company_label(company_name: str, fallback: str) -> str:
    base = company_name.split(" (")[0].strip()
    for suffix in (" Developers Ltd", " India Ltd", " Intl", " Ltd"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base or fallback


def _friendly_agent_label(executor_id: str) -> str:
    mapping = {
        "shockanalyst": "Step 1: Understand the Price Spike",
        "exposureinvestigator": "Step 2: Calculate Domino Impact",
        "riskchallenger": "Step 3: Spot Data Gaps & Risks",
        "reportsynthesizer": "Step 4: Write Summary Report",
    }
    return mapping.get(executor_id.strip().lower(), executor_id)


def _build_company_story(sel: dict[str, Any]) -> list[str]:
    """Generates 3 plain-English bullet points explaining a company's risk story."""
    name = _short_company_label(str(sel.get("company_name", "")), str(sel.get("company_id", "")))
    hop = int(sel.get("hop", -1))
    if hop == 0:
        why = f"**Why It's Affected:** {name} is hit **directly** by the {sel['effective_shock_pct']}% cost increase in {sel['sector']}."
    elif hop >= 1:
        why = (
            f"**Why It's Affected:** {name} sits **{hop} step(s) downstream** (`{sel['path']}`), "
            f"absorbing an estimated **{sel['effective_shock_pct']}%** effective cost increase."
        )
    else:
        why = f"**Why It's Affected:** {name} is **not connected** to this supply chain path within the selected depth."

    money = (
        f"**Money Impact:** Operating profit buffer moves from **₹{sel['base_ebitda_cr']:,.1f} Cr** to "
        f"**₹{sel['stressed_ebitda_cr']:,.1f} Cr**, shifting its loan safety ratio from **{sel['base_dscr']:.2f}x** "
        f"to **{sel['stressed_dscr']:.2f}x** (bank minimum: **{sel['covenant_min_dscr']:.2f}x**)."
    )

    ev_list = sel.get("evidence") or []
    if ev_list:
        ev_refs = ", ".join(
            f"`{e.get('doc_id')}` (conf {float(e.get('confidence', 0.0)):.2f})"
            for e in ev_list
        )
        proof = f"**Source Proof:** Backed by filing evidence {ev_refs}."
    else:
        proof = "**Source Proof:** No direct supply-link filing triggered for this scenario."

    return [why, money, proof]


def build_dscr_comparison_figure(rows: list[dict[str, Any]]) -> go.Figure:
    """Dark-themed grouped bar chart comparing Base DSCR, Stressed DSCR, and Min Covenant."""
    names = [_short_company_label(str(r.get("company_name", "")), r["company_id"]) for r in rows]
    base_vals = [float(r.get("base_dscr", 0.0)) for r in rows]
    stressed_vals = [float(r.get("stressed_dscr", 0.0)) for r in rows]
    min_vals = [float(r.get("covenant_min_dscr", 0.0)) for r in rows]
    stressed_colors = [
        "#EF4444" if r.get("covenant_breach") else "#22C55E"
        for r in rows
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Before Price Spike (Base DSCR)",
            x=names,
            y=base_vals,
            marker_color="#64748B",
        )
    )
    fig.add_trace(
        go.Bar(
            name="After Price Spike (Stressed DSCR)",
            x=names,
            y=stressed_vals,
            marker_color=stressed_colors,
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Bank Safety Minimum",
            x=names,
            y=min_vals,
            mode="lines+markers",
            line={"color": "#F59E0B", "width": 2.5, "dash": "dash"},
            marker={"size": 7, "color": "#F59E0B"},
        )
    )
    fig.update_layout(
        title={"text": "<b>Loan Safety Ratio: Before vs. After Price Spike</b>", "font": {"size": 15, "color": "#F8FAFC"}},
        barmode="group",
        height=360,
        margin={"l": 20, "r": 20, "t": 48, "b": 25},
        plot_bgcolor="#0F172A",
        paper_bgcolor="#0F172A",
        font={"color": "#CBD5E1"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        yaxis={"title": "Loan Safety Ratio (x)", "gridcolor": "rgba(148, 163, 184, 0.15)"},
        xaxis={"gridcolor": "rgba(148, 163, 184, 0.08)"},
    )
    return fig


def _extract_shock_pct(prompt: str, fallback: float = 20.0) -> float:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", prompt)
    if match:
        return float(match.group(1))
    return fallback


def compute_full_stress_table(
    services: dict[str, Any],
    shock_pct: float,
    primary_sector: str = "Steel",
    max_hops: int = 2,
) -> list[dict[str, Any]]:
    """Computes exact deterministic stress rows for all 10 companies + path metadata."""
    i360: I360Adapter = services["i360"]
    covenant: CovenantGuardAdapter = services["covenant"]
    xmine: DataXMineAdapter = services["xmine"]
    models: ModelInfinityAdapter = services["models"]
    graph: SupplyChainGraphEngine = services["graph"]
    financial: FinancialStressEngine = services["financial"]

    all_companies = i360.list_companies()
    seed_companies = i360.list_companies(sector=primary_sector)
    seed_ids = {c.company_id for c in seed_companies}
    downstream_paths = graph.traverse_exposure(list(seed_ids), max_hops=max_hops)

    # Best (highest pass-through) path per downstream company
    best_path_by_company: dict[str, dict[str, Any]] = {}
    all_paths_by_company: dict[str, list[dict[str, Any]]] = {}
    for p in downstream_paths:
        cid = p["company_id"]
        all_paths_by_company.setdefault(cid, []).append(p)
        if cid not in best_path_by_company or (
            p["cumulative_pass_through"] > best_path_by_company[cid]["cumulative_pass_through"]
        ):
            best_path_by_company[cid] = p

    all_models = [m.model_dump() for m in models.list_models()]

    rows: list[dict[str, Any]] = []
    for comp in all_companies:
        cid = comp.company_id
        cov = covenant.get_by_company(cid)
        docs = xmine.list_documents(company_id=cid)

        if cid in seed_ids:
            hop = 0
            path_str = cid
            factor = 1.0
            is_direct = True
            rel = "DIRECT_SHOCK"
            dep_pct = 100.0
            evidence = [
                {
                    "from": "SHOCK_EVENT",
                    "to": cid,
                    "doc_id": "i360-SHOCK-FEED",
                    "confidence": 1.0,
                    "quote": f"Direct {shock_pct:.1f}% input shock in {comp.sector}.",
                }
            ]
        elif cid in best_path_by_company:
            best = best_path_by_company[cid]
            hop = int(best["hop"])
            path_str = str(best["path"])
            factor = float(best["cumulative_pass_through"])
            is_direct = False
            rel = str(best["relationship"])
            dep_pct = float(best["direct_dependency_pct"])
            evidence = list(best["evidence"])
        else:
            hop = -1
            path_str = f"Unreached within {max_hops} hops"
            factor = 0.0
            is_direct = False
            rel = "NONE"
            dep_pct = 0.0
            evidence = []

        metrics = financial.stress_company(
            company=comp,
            shock_pct=shock_pct,
            pass_through_factor=factor,
            is_direct_shock=is_direct,
            covenant_record=cov,
        )

        rows.append(
            {
                **metrics,
                "hop": hop,
                "path": path_str,
                "relationship": rel,
                "direct_dependency_pct": dep_pct,
                "cumulative_pass_through": factor,
                "evidence": evidence,
                "all_paths": all_paths_by_company.get(cid, []),
                "documents": [d.model_dump() for d in docs],
                "model_metadata": all_models,
                "covenant_record": cov.model_dump() if cov else {},
                "raw_financial": comp.model_dump(),
            }
        )

    return rows


def _status_color(row: dict[str, Any]) -> str:
    if row.get("covenant_breach"):
        return "#DC2626"  # Red for stressed covenant breach
    if row.get("prior_covenant_status") == "WATCH":
        return "#D97706"  # Amber for WATCH
    return "#16A34A"  # Green for COMPLIANT


def build_contagion_figure(
    rows: list[dict[str, Any]],
    edges: list[Any],
    selected_company_id: str | None = None,
    mode: str = "full",
) -> go.Figure:
    """
    Builds a Plotly network graph.
    - mode == 'full': all 10 companies and all directed supply edges.
    - mode == 'company': highlights selected_company_id plus all upstream/downstream nodes & edges connected to it.
    """
    row_by_id = {r["company_id"]: r for r in rows}

    # Determine highlighted nodes & edges when inspecting a specific company
    active_nodes: set[str] = set(HOP_COORDS.keys())
    active_edges: set[tuple[str, str]] = {(e.source_id, e.target_id) for e in edges}

    if mode == "company" and selected_company_id:
        active_nodes = {selected_company_id}
        active_edges = set()
        # Upstream (predecessors up to 2 steps)
        frontier_up = {selected_company_id}
        for _ in range(2):
            next_up: set[str] = set()
            for e in edges:
                if e.target_id in frontier_up:
                    active_edges.add((e.source_id, e.target_id))
                    active_nodes.add(e.source_id)
                    next_up.add(e.source_id)
            frontier_up = next_up
        # Downstream (successors up to 2 steps)
        frontier_down = {selected_company_id}
        for _ in range(2):
            next_down: set[str] = set()
            for e in edges:
                if e.source_id in frontier_down:
                    active_edges.add((e.source_id, e.target_id))
                    active_nodes.add(e.target_id)
                    next_down.add(e.target_id)
            frontier_down = next_down

    fig = go.Figure()

    # Draw edges
    for e in edges:
        src, dst = e.source_id, e.target_id
        if src not in HOP_COORDS or dst not in HOP_COORDS:
            continue
        x0, y0, _ = HOP_COORDS[src]
        x1, y1, _ = HOP_COORDS[dst]
        is_highlighted = (src, dst) in active_edges

        line_color = "#38BDF8" if (mode == "company" and is_highlighted) else (
            "#64748B" if mode == "full" else "#1E293B"
        )
        line_width = 3.2 if (mode == "company" and is_highlighted) else (
            1.8 if mode == "full" else 1.0
        )

        fig.add_trace(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line={"color": line_color, "width": line_width},
                hoverinfo="text",
                text=(
                    f"{src} -> {dst} [{e.relationship}]<br>"
                    f"Dependency: {e.dependency_pct * 100:.0f}% | Doc: {e.evidence_doc_id} "
                    f"(conf: {e.confidence:.2f})<br>"
                    f"Quote: {e.evidence_quote}"
                ),
                showlegend=False,
            )
        )

        # Midpoint label for dependency & doc_id on highlighted/full edges
        if mode == "full" or is_highlighted:
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0 + 0.12
            fig.add_trace(
                go.Scatter(
                    x=[mx],
                    y=[my],
                    mode="text",
                    text=[f"{int(e.dependency_pct * 100)}% ({e.evidence_doc_id})"],
                    textfont={"size": 10, "color": "#E2E8F0" if is_highlighted else "#94A3B8"},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    # Draw nodes
    node_x, node_y, node_colors, node_sizes, node_labels, node_hovers, node_borders = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for cid, (x, y, hop) in HOP_COORDS.items():
        r = row_by_id.get(cid, {})
        in_scope = cid in active_nodes
        base_col = _status_color(r)

        if mode == "company":
            if cid == selected_company_id:
                col = base_col
                border_col = "#F8FAFC"
                size = 28
            elif in_scope:
                col = base_col
                border_col = "#38BDF8"
                size = 22
            else:
                col = "#334155"
                border_col = "#475569"
                size = 16
        else:
            col = base_col
            border_col = "#38BDF8" if cid == selected_company_id else "#0F172A"
            size = 24 if cid == selected_company_id else 20

        node_x.append(x)
        node_y.append(y)
        node_colors.append(col)
        node_sizes.append(size)
        node_borders.append(border_col)
        short_name = _short_company_label(str(r.get("company_name", "")), cid)
        dscr_val = r.get("stressed_dscr", "N/A")
        if r.get("covenant_breach"):
            status_tag = f"🔴 AT RISK ({dscr_val}x)"
        elif r.get("prior_covenant_status") == "WATCH":
            status_tag = f"🟡 WATCH ({dscr_val}x)"
        else:
            status_tag = f"🟢 SAFE ({dscr_val}x)"
        node_labels.append(f"{short_name}<br>{status_tag}")
        node_hovers.append(
            f"<b>{r.get('company_name', cid)} ({cid})</b><br>"
            f"Sector: {r.get('sector', 'N/A')} | Hop: {hop}<br>"
            f"Path: {r.get('path', 'N/A')}<br>"
            f"Base DSCR: {r.get('base_dscr')} -> Stressed DSCR: {r.get('stressed_dscr')} "
            f"(Min: {r.get('covenant_min_dscr')})<br>"
            f"Breach: {r.get('covenant_breach')} | Margin: {r.get('base_margin_pct')}% -> "
            f"{r.get('stressed_margin_pct')}%<br>"
            f"WC Drag: ₹{r.get('wc_receivables_drag_cr')} Cr"
        )

    fig.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            marker={
                "size": node_sizes,
                "color": node_colors,
                "line": {"width": 2.5, "color": node_borders},
            },
            text=node_labels,
            textposition="top center",
            textfont={"size": 10, "color": "#F1F5F9"},
            hovertext=node_hovers,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_layout(
        title={
            "text": (
                f"<b>Selected Company Subgraph: {selected_company_id}</b>"
                if mode == "company" and selected_company_id
                else "<b>Full Supply Chain Contagion Network</b>"
            ),
            "font": {"size": 15, "color": "#F8FAFC"},
        },
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "range": [-0.8, 5.2]},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False, "range": [-4.2, 5.15]},
        height=580,
        margin={"l": 14, "r": 14, "t": 50, "b": 14},
        plot_bgcolor="#0F172A",
        paper_bgcolor="#0F172A",
        annotations=[
            {
                "x": 0.0,
                "y": 4.55,
                "text": "<b>Hop 0</b><br>Direct Impact",
                "showarrow": False,
                "font": {"size": 11, "color": "#94A3B8"},
            },
            {
                "x": 2.2,
                "y": 4.55,
                "text": "<b>Hop 1</b><br>Tier-1 Suppliers",
                "showarrow": False,
                "font": {"size": 11, "color": "#94A3B8"},
            },
            {
                "x": 4.4,
                "y": 4.55,
                "text": "<b>Hop 2</b><br>OEMs & Metro",
                "showarrow": False,
                "font": {"size": 11, "color": "#94A3B8"},
            },
        ],
    )
    return fig


async def _execute_workflow_trace(
    prompt: str,
    llm_config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Runs the MAF SequentialBuilder workflow and captures step-by-step agent traces."""
    workflow = build_contagion_workflow(llm_config=llm_config)
    step_logs: list[dict[str, str]] = []
    report_chunks: list[str] = []
    final_report = ""

    async for event in workflow.run(prompt, stream=True):
        event_type = getattr(event, "type", type(event).__name__)
        executor_id = getattr(event, "executor_id", None) or str(event_type)
        data = getattr(event, "data", None)

        if event_type == "output" and isinstance(data, AgentResponseUpdate):
            if executor_id == "reportsynthesizer" and data.text:
                report_chunks.append(data.text)
        elif event_type == "executor_completed" and isinstance(data, list):
            text = "".join(
                update.text
                for update in data
                if isinstance(update, AgentResponseUpdate) and update.text
            ).strip()
            if text:
                if executor_id == "reportsynthesizer":
                    final_report = text
                step_logs.append(
                    {
                        "event_type": str(event_type),
                        "executor": str(executor_id),
                        "content": text,
                    }
                )

    if not final_report:
        final_report = "".join(report_chunks).strip()
    if not final_report and step_logs:
        final_report = step_logs[-1]["content"]

    return step_logs, final_report


def run_workflow_sync(
    prompt: str,
    llm_config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], str]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _execute_workflow_trace(prompt, llm_config=llm_config)).result()
    except RuntimeError:
        pass
    return asyncio.run(_execute_workflow_trace(prompt, llm_config=llm_config))


def _inject_premium_theme() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
            max-width: 1380px;
        }
        .ciq-hero {
            background: linear-gradient(135deg, #0F172A 0%, #1E293B 55%, #1E3A5F 100%);
            border-radius: 16px;
            padding: 1.5rem 1.75rem;
            color: #F8FAFC;
            margin-bottom: 1.25rem;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
            border: 1px solid rgba(148, 163, 184, 0.22);
        }
        .ciq-hero h1 {
            margin: 0;
            font-size: 1.85rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #FFFFFF;
        }
        .ciq-hero p {
            margin: 0.45rem 0 0.85rem 0;
            color: #CBD5E1;
            font-size: 0.95rem;
        }
        .ciq-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .ciq-badge {
            background: rgba(56, 189, 248, 0.14);
            border: 1px solid rgba(56, 189, 248, 0.35);
            color: #E0F2FE;
            padding: 0.22rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        div[data-testid="stMetric"] {
            background: rgba(30, 41, 59, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 12px;
            padding: 0.85rem 1rem;
            box-shadow: 0 4px 14px rgba(2, 6, 23, 0.28);
        }
        div[data-testid="stMetricLabel"] {
            font-weight: 600;
            color: #94A3B8;
        }
        div[data-testid="stMetricValue"] {
            color: #F8FAFC;
            font-weight: 700;
        }
        button[data-baseweb="tab"] {
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _sync_streamlit_secrets() -> None:
    """Loads top-level Streamlit Cloud secrets into os.environ when deployed."""
    try:
        for key, value in st.secrets.items():
            if isinstance(value, str) and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def main() -> None:
    _sync_streamlit_secrets()
    os.environ["CONTAGIONIQ_DATA_DIR"] = str(ROOT_DIR / "data_india")
    st.set_page_config(
        page_title="ContagionIQ — Supply Chain & Credit Contagion Workbench",
        layout="wide",
    )
    _inject_premium_theme()

    services = get_services("india")
    i360: I360Adapter = services["i360"]
    xmine: DataXMineAdapter = services["xmine"]
    all_companies = i360.list_companies()
    company_options = [f"{c.company_id} — {c.company_name}" for c in all_companies]
    id_by_option = {f"{c.company_id} — {c.company_name}": c.company_id for c in all_companies}

    expected_ids = {c.company_id for c in all_companies}
    if (
        "stress_rows" not in st.session_state
        or {r.get("company_id") for r in st.session_state["stress_rows"]} != expected_ids
    ):
        st.session_state["stress_rows"] = compute_full_stress_table(services, shock_pct=20.0)
    if "agent_traces" not in st.session_state:
        st.session_state["agent_traces"] = []
    if "final_report" not in st.session_state:
        st.session_state["final_report"] = ""
    if "hitl_status" not in st.session_state:
        st.session_state["hitl_status"] = "PENDING_REVIEW"
    if "last_run_id" not in st.session_state:
        st.session_state["last_run_id"] = ""
    if "last_duration_sec" not in st.session_state:
        st.session_state["last_duration_sec"] = 0.0

    llm_config = _render_llm_sidebar()
    provider_badge = _get_active_provider_label(llm_config)
    st.markdown(
        f"""
        <div class="ciq-hero">
            <h1>ContagionIQ — Supply Chain &amp; Credit Risk Workbench</h1>
            <p>See how a raw-material price spike ripples through suppliers, auto makers, and builders—combining exact financial math with a 4-step AI review and human approval.</p>
            <div class="ciq-badges">
                <span class="ciq-badge">1. Enter Price Shock</span>
                <span class="ciq-badge">2. Trace Domino Impact</span>
                <span class="ciq-badge">3. AI Risk Review</span>
                <span class="ciq-badge">4. Human Approval &amp; History</span>
                <span class="ciq-badge">{provider_badge}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "prompt_text_input" not in st.session_state:
        st.session_state["prompt_text_input"] = DEFAULT_PROMPT
    if "shock_override_input" not in st.session_state:
        st.session_state["shock_override_input"] = 20.0

    # Quick Scenario Presets
    p_col1, p_col2, p_col3 = st.columns(3)
    with p_col1:
        if st.button("Preset: Coking Coal +20% (Steel)", width="stretch"):
            st.session_state["prompt_text_input"] = DEFAULT_PROMPT
            st.session_state["shock_override_input"] = 20.0
    with p_col2:
        if st.button("Preset: Mild Input +10% (Steel)", width="stretch"):
            st.session_state["prompt_text_input"] = (
                "Coking coal prices increased by 10% due to port congestion. "
                "Investigate direct and 2-hop downstream contagion across Steel, Auto Components, Auto OEMs, and Infrastructure."
            )
            st.session_state["shock_override_input"] = 10.0
    with p_col3:
        if st.button("Preset: Severe Spike +35% (Steel)", width="stretch"):
            st.session_state["prompt_text_input"] = (
                "Coking coal prices surged by 35% due to severe export restrictions. "
                "Investigate direct and 2-hop downstream contagion across Steel, Auto Components, Auto OEMs, and Infrastructure."
            )
            st.session_state["shock_override_input"] = 35.0

    sector_options = sorted({c.sector for c in all_companies})
    default_sector_idx = sector_options.index("Steel") if "Steel" in sector_options else 0

    # Top Control Bar
    with st.container(border=True):
        col_in, col_ctrl = st.columns([3, 1])
        with col_in:
            prompt_text = st.text_area(
                "Price Spike Scenario (What Happened?)",
                key="prompt_text_input",
                height=112,
            )
        with col_ctrl:
            primary_sector = st.selectbox("Starting Affected Industry", options=sector_options, index=default_sector_idx)
            shock_override = st.number_input(
                "Cost Increase (%)",
                min_value=0.0,
                max_value=100.0,
                key="shock_override_input",
                step=1.0,
            )
            max_hops = st.selectbox("Supply Chain Depth (Steps)", options=[1, 2], index=1)
            run_clicked = st.button("Run Ripple Impact Analysis", type="primary", width="stretch")

    audit_logger: InvestigationAuditLogger = services["audit"]

    if run_clicked:
        t0 = time.perf_counter()
        computed_rows = compute_full_stress_table(
            services,
            shock_pct=float(shock_override),
            primary_sector=primary_sector,
            max_hops=int(max_hops),
        )
        st.session_state["stress_rows"] = computed_rows
        with st.status("Running 4-Agent Sequential Workflow (ShockAnalyst -> ExposureInvestigator -> RiskChallenger -> ReportSynthesizer)...", expanded=True) as status_box:
            try:
                traces, report = run_workflow_sync(prompt_text, llm_config=llm_config)
                duration_sec = time.perf_counter() - t0
                st.session_state["agent_traces"] = traces
                st.session_state["final_report"] = report
                st.session_state["hitl_status"] = "AWAITING_HUMAN_APPROVAL"
                audit_entry = audit_logger.record_run(
                    prompt=prompt_text,
                    shock_pct=float(shock_override),
                    max_hops=int(max_hops),
                    stress_rows=computed_rows,
                    agent_step_count=len(traces),
                    hitl_status="AWAITING_HUMAN_APPROVAL",
                    duration_sec=duration_sec,
                )
                st.session_state["last_run_id"] = audit_entry["run_id"]
                st.session_state["last_duration_sec"] = audit_entry["duration_sec"]
                status_box.update(
                    label=f"Investigation complete ({audit_entry['run_id']}, {audit_entry['duration_sec']}s) — full trace captured.",
                    state="complete",
                )
            except Exception as exc:
                status_box.update(label="AI workflow paused — deterministic stress math updated below.", state="error")
                st.error(
                    f"The AI workflow encountered a temporary provider error (`{type(exc).__name__}`): {exc}. "
                    "Deterministic stress numbers and graphs above are still updated; please retry in a few seconds or switch `LLM_PROVIDER` in `.env`."
                )

    rows: list[dict[str, Any]] = st.session_state["stress_rows"]
    row_by_id = {r["company_id"]: r for r in rows}

    # KPI Strip
    breach_count = sum(1 for r in rows if r.get("covenant_breach"))
    hop1_2_count = sum(1 for r in rows if r.get("hop", -1) >= 1)
    max_wc_drag = max((float(r.get("wc_receivables_drag_cr", 0.0)) for r in rows), default=0.0)
    total_debt_cr = sum(float(r.get("raw_financial", {}).get("debt_cr", 0.0)) for r in rows)
    debt_at_risk_cr = sum(
        float(r.get("raw_financial", {}).get("debt_cr", 0.0))
        for r in rows
        if r.get("covenant_breach")
    )
    debt_at_risk_pct = (debt_at_risk_cr / total_debt_cr * 100.0) if total_debt_cr > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Companies Tracked",
        len(rows),
        help="Total companies tracked across Steel, Auto Parts, Auto Makers, and Infrastructure.",
    )
    k2.metric(
        "At-Risk Companies",
        breach_count,
        help="Companies whose operating profit falls below the safety minimum required by their bank loan.",
    )
    k3.metric(
        "Loan Exposure at Risk",
        f"₹{debt_at_risk_cr:,.0f} Cr",
        delta=f"{debt_at_risk_pct:.0f}% of ₹{total_debt_cr:,.0f} Cr",
        delta_color="inverse",
        help="Total debt held by companies projected to fall below their bank loan safety limit.",
    )
    k4.metric(
        "Downstream Customers Hit",
        hop1_2_count,
        help="Companies indirectly affected 1 or 2 steps down the supply chain from the initial price spike.",
    )
    k5.metric(
        "Peak Cash Tied in Bills",
        f"₹{max_wc_drag:.2f} Cr",
        help="Extra cash tied up in unpaid customer bills when payments slow down during a price spike.",
    )

    direct_breaches = sum(1 for r in rows if r.get("hop") == 0 and r.get("covenant_breach"))
    downstream_breaches = sum(1 for r in rows if r.get("hop", -1) >= 1 and r.get("covenant_breach"))
    safe_count = len(rows) - breach_count
    st.info(
        f"**Plain-English Summary:** A **{float(shock_override):.0f}%** raw-material price spike puts "
        f"**{breach_count} of {len(rows)} companies** below their bank loan safety buffer "
        f"(**{direct_breaches}** direct producers and **{downstream_breaches}** downstream suppliers/builders), "
        f"while **{safe_count}** companies remain financially safe."
    )

    at_risk_names = [
        _short_company_label(str(r.get("company_name", "")), r["company_id"])
        for r in rows
        if r.get("covenant_breach")
    ]
    watch_names = [
        _short_company_label(str(r.get("company_name", "")), r["company_id"])
        for r in rows
        if not r.get("covenant_breach") and r.get("prior_covenant_status") == "WATCH"
    ]
    safe_names = [
        _short_company_label(str(r.get("company_name", "")), r["company_id"])
        for r in rows
        if not r.get("covenant_breach") and r.get("prior_covenant_status") != "WATCH"
    ]
    b1, b2, b3 = st.columns(3)
    with b1:
        with st.container(border=True):
            st.markdown(f"**🔴 At Risk ({len(at_risk_names)})**")
            st.caption(", ".join(at_risk_names) if at_risk_names else "None")
    with b2:
        with st.container(border=True):
            st.markdown(f"**🟡 Watch Closely ({len(watch_names)})**")
            st.caption(", ".join(watch_names) if watch_names else "None")
    with b3:
        with st.container(border=True):
            st.markdown(f"**🟢 Safe ({len(safe_names)})**")
            st.caption(", ".join(safe_names) if safe_names else "None")

    with st.expander("Plain-English Guide: What Do These Terms Mean?", expanded=False):
        st.markdown(
            "- **DSCR (Loan Safety Ratio):** Operating profit divided by yearly loan payments. "
            "Above **1.0x** means the company earns enough to pay its debt; dropping below **Min DSCR** triggers a **Breach** (bank warning/review).\n"
            "- **Hop 0 / 1 / 2 (Domino Steps):** **Hop 0** = companies hit directly; **Hop 1** = their direct customers; **Hop 2** = customers two steps down the chain.\n"
            "- **Pass-Through:** Share of the supplier's cost increase passed on to the next buyer.\n"
            "- **Margin & bps:** Profit % on sales (**100 bps = 1%** change in profit margin).\n"
            "- **WC Drag (₹ Cr):** Extra cash stuck waiting for customers to pay their invoices."
        )

    st.divider()

    # Section 1: Full Supply Chain Graph + Company Selector Subgraph
    st.subheader("1. Supply Chain Ripple Map & Company View")
    selected_option = st.selectbox(
        "Select Any Company to Trace Its Exact Subgraph, Evidence, & Stress Math",
        options=company_options,
        index=3,  # Default to AUTO_SUP_B so a breach + multi-hop link is immediately visible
    )
    selected_cid = id_by_option[selected_option]

    st.caption(
        "Node Colors: **Red** = At Risk (Loan Safety Limit Breached) | **Amber** = Watch Closely | **Green** = Safe"
    )
    g_col1, g_col2 = st.columns(2)
    with g_col1:
        with st.container(border=True):
            st.plotly_chart(
                build_contagion_figure(rows, xmine.list_edges(), selected_company_id=selected_cid, mode="full"),
                width="stretch",
            )
    with g_col2:
        with st.container(border=True):
            st.plotly_chart(
                build_contagion_figure(rows, xmine.list_edges(), selected_company_id=selected_cid, mode="company"),
                width="stretch",
            )

    # Section 2: Complete Trace for Selected Company (Zero Omissions)
    st.subheader(f"2. Complete End-to-End Trace — {selected_cid}")
    sel = row_by_id[selected_cid]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(
        "Hop Depth",
        str(sel["hop"]),
        help="0 = hit directly by the price shock; 1 = direct customer; 2 = two steps downstream.",
    )
    m2.metric(
        "Base DSCR",
        f"{sel['base_dscr']:.2f}",
        help="Normal loan safety ratio (operating profit ÷ yearly loan payments) before the shock.",
    )
    m3.metric(
        "Stressed DSCR",
        f"{sel['stressed_dscr']:.2f}",
        delta=f"{sel['stressed_dscr'] - sel['base_dscr']:+.2f}",
        help="Loan safety ratio after the price shock.",
    )
    m4.metric(
        "Min Covenant DSCR",
        f"{sel['covenant_min_dscr']:.2f}",
        help="Minimum ratio required by the bank loan agreement.",
    )
    m5.metric(
        "Covenant Breach",
        "YES (BREACH)" if sel["covenant_breach"] else "NO",
        help="YES means the stressed ratio fell below the bank's minimum safety requirement.",
    )

    verdict = (
        f"**At Risk** — its loan safety ratio drops from **{sel['base_dscr']:.2f}x** to **{sel['stressed_dscr']:.2f}x** "
        f"(below the **{sel['covenant_min_dscr']:.2f}x** bank minimum)."
        if sel["covenant_breach"]
        else f"**Safe** — its loan safety ratio shifts from **{sel['base_dscr']:.2f}x** to **{sel['stressed_dscr']:.2f}x**, "
        f"staying above the **{sel['covenant_min_dscr']:.2f}x** bank minimum."
    )
    st.caption(f"Plain-English Verdict for **{sel['company_name']}**: {verdict}")

    with st.container(border=True):
        st.markdown(f"**3-Point Story for {_short_company_label(str(sel.get('company_name', '')), selected_cid)}**")
        for bullet in _build_company_story(sel):
            st.markdown(f"- {bullet}")

    t_path, t_fin, t_cov, t_doc, t_mod = st.tabs(
        [
            "Graph Paths & Pass-Through",
            "i360 & Stress Math",
            "Covenant Guard & EWS",
            "Data XMine Evidence",
            "Model Infinity Governance",
        ]
    )

    with t_path:
        st.write(f"**Primary Contagion Path:** `{sel['path']}`")
        st.write(
            f"**Relationship:** `{sel['relationship']}` | "
            f"**Direct Dependency:** `{sel['direct_dependency_pct']}%` | "
            f"**Cumulative Pass-Through:** `{sel['cumulative_pass_through']}` | "
            f"**Effective Shock:** `{sel['effective_shock_pct']}%`"
        )
        st.write("**Step-by-Step Edge Evidence Trail:**")
        st.json(sel["evidence"])
        if sel["all_paths"]:
            st.write("**All Discovered Paths to This Company:**")
            st.json(sel["all_paths"])

    with t_fin:
        st.write("**Deterministic Stress Engine Output:**")
        st.json(
            {
                "base_ebitda_cr": sel["base_ebitda_cr"],
                "stressed_ebitda_cr": sel["stressed_ebitda_cr"],
                "base_margin_pct": sel["base_margin_pct"],
                "stressed_margin_pct": sel["stressed_margin_pct"],
                "margin_change_bps": sel["margin_change_bps"],
                "wc_receivables_drag_cr": sel["wc_receivables_drag_cr"],
                "covenant_breach": sel["covenant_breach"],
            }
        )
        st.write("**Raw i360 Company Record:**")
        st.json(sel["raw_financial"])

    with t_cov:
        st.write("**Active EWS Signals:**")
        st.write(sel["active_ews_signals"] if sel["active_ews_signals"] else ["None"])
        st.write("**Full Covenant Guard Record:**")
        st.json(sel["covenant_record"])

    with t_doc:
        st.write("**Extracted Data XMine Documents:**")
        st.json(sel["documents"])

    with t_mod:
        st.write("**Model Infinity Validation & Drift Metadata:**")
        st.json(sel["model_metadata"])

    st.divider()

    # Section 3: Portfolio-Wide Deterministic Stress Matrix
    st.subheader("3. All Companies — Financial Impact Summary")
    with st.container(border=True):
        st.plotly_chart(build_dscr_comparison_figure(rows), width="stretch")

    summary_df = pd.DataFrame(
        [
            {
                "Company ID": r["company_id"],
                "Company Name": r["company_name"],
                "Sector": r["sector"],
                "Hop": r["hop"],
                "Path": r["path"],
                "Eff. Shock (%)": r["effective_shock_pct"],
                "Base Margin (%)": r["base_margin_pct"],
                "Stressed Margin (%)": r["stressed_margin_pct"],
                "Base DSCR": r["base_dscr"],
                "Stressed DSCR": r["stressed_dscr"],
                "Min DSCR": r["covenant_min_dscr"],
                "Safety Margin Left (%)": (
                    round(((r["stressed_dscr"] - r["covenant_min_dscr"]) / r["covenant_min_dscr"]) * 100.0, 1)
                    if r["covenant_min_dscr"] > 0
                    else 0.0
                ),
                "Risk Status": (
                    "🔴 At Risk"
                    if r["covenant_breach"]
                    else ("🟡 Watch" if r.get("prior_covenant_status") == "WATCH" else "🟢 Safe")
                ),
                "WC Drag (₹ Cr)": r["wc_receivables_drag_cr"],
            }
            for r in rows
        ]
    )
    st.dataframe(summary_df, width="stretch", hide_index=True)
    st.download_button(
        "Download Stress Matrix (CSV)",
        data=summary_df.to_csv(index=False).encode("utf-8"),
        file_name="contagioniq_stress_matrix.csv",
        mime="text/csv",
    )

    st.divider()

    # Section 4: Agent-by-Agent Execution Trace + Final Report + HITL Approval Gate
    st.subheader("4. AI Investigation Report & Analyst Sign-Off")

    if st.session_state["agent_traces"]:
        with st.expander("Inspect Every AI Step", expanded=False):
            for idx, item in enumerate(st.session_state["agent_traces"], start=1):
                friendly_name = _friendly_agent_label(str(item["executor"]))
                st.markdown(f"**{friendly_name}** (`{item['executor']}`)")
                st.markdown(item["content"])
                st.markdown("---")
    else:
        st.info("Click **Run Contagion Investigation** above to execute the live 4-agent Gemini workflow and capture every agent step.")

    if st.session_state["final_report"]:
        st.markdown("### Synthesized Investigation Report")
        st.markdown(st.session_state["final_report"])
        st.download_button(
            "Download Report (Markdown)",
            data=st.session_state["final_report"].encode("utf-8"),
            file_name="contagioniq_report.md",
            mime="text/markdown",
        )

    st.markdown("### Human-in-the-Loop (HITL) Publication Gate (`publish_investigation_report`)")
    st.write(f"**Current Gate Status:** `{st.session_state['hitl_status']}`")
    breached_names = [
        f"{r['company_id']} ({r['company_name']})"
        for r in rows
        if r.get("covenant_breach")
    ]
    h_col1, h_col2 = st.columns(2)
    with h_col1:
        if st.button("Approve & Publish to EI Review Queue", type="primary", width="stretch"):
            summary_text = (
                f"{float(shock_override):.1f}% shock ({int(max_hops)} hops): "
                f"{breach_count} covenant breaches ({', '.join(r['company_id'] for r in rows if r.get('covenant_breach')) or 'None'})."
            )
            publish_investigation_report.func(
                report_title=f"ContagionIQ Investigation — {float(shock_override):.1f}% Shock",
                executive_summary=summary_text,
            )
            saved = save_analysis_record(
                {
                    "status": "PUBLISHED",
                    "prompt": prompt_text,
                    "shock_pct": float(shock_override),
                    "max_hops": int(max_hops),
                    "breach_count": breach_count,
                    "breached_companies": breached_names,
                    "final_report": st.session_state["final_report"] or summary_text,
                    "agent_traces": st.session_state["agent_traces"],
                    "stress_summary": [
                        {
                            "Company ID": r["company_id"],
                            "Company Name": r["company_name"],
                            "Sector": r["sector"],
                            "Hop": r["hop"],
                            "Base DSCR": r["base_dscr"],
                            "Stressed DSCR": r["stressed_dscr"],
                            "Min DSCR": r["covenant_min_dscr"],
                            "Breach": r["covenant_breach"],
                        }
                        for r in rows
                    ],
                }
            )
            st.session_state["hitl_status"] = f"PUBLISHED ({saved['analysis_id']})"
            st.success(
                f"Report approved, published, and saved persistently as `{saved['analysis_id']}`."
            )
    with h_col2:
        if st.button("Hold / Request Analyst Revision", width="stretch"):
            saved = save_analysis_record(
                {
                    "status": "HELD",
                    "prompt": prompt_text,
                    "shock_pct": float(shock_override),
                    "max_hops": int(max_hops),
                    "breach_count": breach_count,
                    "breached_companies": breached_names,
                    "final_report": st.session_state["final_report"]
                    or f"Held for revision ({float(shock_override):.1f}% shock, {breach_count} breaches).",
                    "agent_traces": st.session_state["agent_traces"],
                    "stress_summary": [
                        {
                            "Company ID": r["company_id"],
                            "Company Name": r["company_name"],
                            "Sector": r["sector"],
                            "Hop": r["hop"],
                            "Base DSCR": r["base_dscr"],
                            "Stressed DSCR": r["stressed_dscr"],
                            "Min DSCR": r["covenant_min_dscr"],
                            "Breach": r["covenant_breach"],
                        }
                        for r in rows
                    ],
                }
            )
            st.session_state["hitl_status"] = f"HELD ({saved['analysis_id']})"
            st.warning(f"Report placed on hold and saved to history as `{saved['analysis_id']}`.")

    st.divider()

    # Section 5: Persistent Past Analyses & Filters
    st.subheader("5. Past Saved Analyses (Persistent History)")
    all_saved = load_analysis_records()
    if not all_saved:
        st.info("No saved analyses yet. Click **Approve & Publish** or **Hold** above to save one permanently.")
    else:
        available_dates = sorted(
            {str(r.get("saved_date", "")) for r in all_saved if r.get("saved_date")},
            reverse=True,
        )
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            hist_status = st.selectbox("Filter by Status", options=["All", "PUBLISHED", "HELD"])
        with f_col2:
            hist_min_shock = st.number_input("Min Shock (%)", min_value=0.0, max_value=100.0, value=0.0, step=5.0)
        with f_col3:
            hist_date = st.selectbox("Filter by Date", options=["All"] + available_dates)
        with f_col4:
            hist_query = st.text_input("Search Keyword / Company", placeholder="e.g. STEEL_A, coal, OEM")

        filtered_saved = filter_analysis_records(
            all_saved,
            status_filter=hist_status,
            min_shock_pct=float(hist_min_shock),
            search_query=hist_query,
            date_filter=hist_date,
        )

        st.caption(f"Showing **{len(filtered_saved)}** of **{len(all_saved)}** saved analyses (stored in `data/published_analyses.json`).")

        if filtered_saved:
            history_df = pd.DataFrame(
                [
                    {
                        "ID": r.get("analysis_id"),
                        "Saved At": r.get("saved_at"),
                        "Status": r.get("status"),
                        "Shock (%)": r.get("shock_pct"),
                        "Hops": r.get("max_hops"),
                        "Breaches": r.get("breach_count"),
                        "Prompt": str(r.get("prompt", ""))[:80],
                    }
                    for r in filtered_saved
                ]
            )
            st.dataframe(history_df, width="stretch", hide_index=True)

            pick_options = [
                f"{r['analysis_id']} | {r['saved_at']} | {r['status']} | {r['shock_pct']}% shock"
                for r in filtered_saved
            ]
            chosen_label = st.selectbox("Select a Past Analysis to View", options=pick_options)
            chosen_rec = filtered_saved[pick_options.index(chosen_label)]

            with st.container(border=True):
                st.markdown(
                    f"**{chosen_rec['analysis_id']}** — Status: `{chosen_rec['status']}` | "
                    f"Saved: `{chosen_rec['saved_at']}` | Shock: `{chosen_rec['shock_pct']}%` | "
                    f"Breaches: `{chosen_rec['breach_count']}`"
                )
                st.markdown(f"**Prompt:** {chosen_rec.get('prompt', '')}")
                if chosen_rec.get("final_report"):
                    st.markdown("#### Saved Report")
                    st.markdown(chosen_rec["final_report"])
                if chosen_rec.get("stress_summary"):
                    with st.expander("Saved Stress Matrix", expanded=False):
                        st.dataframe(pd.DataFrame(chosen_rec["stress_summary"]), width="stretch", hide_index=True)
                if chosen_rec.get("agent_traces"):
                    with st.expander("Saved Agent Traces", expanded=False):
                        for idx, step in enumerate(chosen_rec["agent_traces"], start=1):
                            st.markdown(f"**Step {idx} — `{step['executor']}`**")
                            st.markdown(step["content"])
                            st.markdown("---")
        else:
            st.warning("No saved analyses match the current filters.")

    st.divider()

    # Section 6: Observability & Audit Telemetry
    st.subheader("6. Observability & Audit Telemetry")
    st.caption("Automatically logs every investigation run—execution speed, source filings cited, and human approval status.")
    recent_audit = audit_logger.recent_runs(limit=20)
    if not recent_audit:
        st.info("No telemetry runs logged yet. Click **Run Ripple Impact Analysis** to record your first audit trace.")
    else:
        avg_latency = sum(float(r.get("duration_sec", 0.0)) for r in recent_audit) / len(recent_audit)
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Logged Runs", len(recent_audit), help="Total investigation runs recorded in logs/investigation_audit.jsonl.")
        o2.metric("Avg Workflow Latency", f"{avg_latency:.2f}s", help="Average end-to-end time taken by the 4-agent AI workflow.")
        o3.metric("Last Run ID", st.session_state.get("last_run_id") or recent_audit[0].get("run_id", "N/A"), help="Unique identifier for the most recent investigation run.")
        o4.metric("Cited Docs (Latest)", len(recent_audit[0].get("cited_documents", [])), help="Number of source filings (DX-*) referenced in the latest run.")

        audit_df = pd.DataFrame(
            [
                {
                    "Run ID": r.get("run_id"),
                    "Timestamp (UTC)": r.get("timestamp_utc"),
                    "Duration (s)": r.get("duration_sec"),
                    "Shock (%)": r.get("shock_pct"),
                    "Hops": r.get("max_hops"),
                    "Agent Steps": r.get("agent_step_count"),
                    "Breaches": r.get("breach_count"),
                    "HITL Status": r.get("hitl_status"),
                    "Cited Docs": ", ".join(r.get("cited_documents", [])),
                }
                for r in recent_audit
            ]
        )
        st.dataframe(audit_df, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()