from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "investigation_audit.jsonl"


class InvestigationAuditLogger:
    """Appends structured JSONL audit & telemetry records for each ContagionIQ run."""

    def __init__(self, log_path: Path = DEFAULT_LOG_PATH) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_run(
        self,
        *,
        prompt: str,
        shock_pct: float,
        max_hops: int,
        stress_rows: list[dict[str, Any]],
        agent_step_count: int,
        hitl_status: str,
        duration_sec: float,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        breached_ids = [r["company_id"] for r in stress_rows if r.get("covenant_breach")]
        cited_docs = sorted(
            {
                ev.get("doc_id")
                for r in stress_rows
                for ev in r.get("evidence", [])
                if str(ev.get("doc_id", "")).startswith("DX-")
            }
        )

        entry = {
            "run_id": run_id or f"RUN-{uuid.uuid4().hex[:8].upper()}",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "duration_sec": round(duration_sec, 2),
            "shock_pct": shock_pct,
            "max_hops": max_hops,
            "agent_step_count": agent_step_count,
            "breach_count": len(breached_ids),
            "breached_companies": breached_ids,
            "cited_documents": cited_docs,
            "hitl_status": hitl_status,
            "prompt": prompt,
        }

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        return list(reversed(records[-limit:]))
