# ContagionIQ — Autonomous Supply Chain & Credit Risk Workbench

**ContagionIQ** is an AI-assisted supply-chain contagion and credit risk analysis workbench. It traces how an upstream commodity or macro price shock (e.g., a +20% surge in coking coal) ripples across **Hop 0** (directly hit producers), **Hop 1** (Tier-1 suppliers & EPC contractors), and **Hop 2** (Auto OEMs & downstream infrastructure) while keeping all financial math deterministic and audit-ready.

---

## Key Capabilities

* **Deterministic Financial & Graph Engines (Zero LLM Number Guessing)**
  * [`SupplyChainGraphEngine`](engine/graph.py) uses NetworkX multi-hop BFS to trace downstream dependencies, cumulative pass-through factors, and filing evidence trails.
  * [`FinancialStressEngine`](engine/financials.py) uses Pandas to compute stressed EBITDA, margin compression (bps), stressed DSCR, covenant breach status, and working-capital receivables drag.
* **4-Agent Sequential AI Workflow (`SequentialBuilder`)**
  * **ShockAnalyst** → **ExposureInvestigator** → **RiskChallenger** → **ReportSynthesizer** ([`agents/workflow.py`](agents/workflow.py)).
  * Audits filing freshness and confidence (`Data XMine`), surfaces model drift & calibration limits (`Model Infinity`), and synthesizes a structured 5-section Markdown report.
* **Interactive Dark-Theme Streamlit Workbench ([`app.py`](app.py))**
  * **Plain-English UX**: Dynamic executive summary, hover tooltips, glossary, and per-company plain-English verdicts so non-finance stakeholders can understand risk immediately.
  * **Visual Analytics**: Dual Plotly supply-chain network graphs (full network + selected-company subgraph) and a grouped **Base vs. Stressed DSCR** bar chart against bank covenant thresholds.
  * **1-Click Presets, Sector Selector & Exports**: Scenario preset buttons, primary sector selector, and 1-click CSV (`contagioniq_stress_matrix.csv`) and Markdown (`contagioniq_report.md`) downloads.
  * **Persistent HITL Approval & Filters**: Approving or holding a report saves the full snapshot to `data/published_analyses.json` with filters for status, minimum shock %, date, and keyword/company search.
  * **Observability & Audit Telemetry**: [`InvestigationAuditLogger`](observability/audit.py) appends structured JSONL telemetry (run ID, UTC timestamp, latency, cited `DX-*` documents, breaches, HITL status) to `logs/investigation_audit.jsonl`.
* **Multi-Provider LLM Support**
  * Supports **Google Gemini** (`GeminiChatClient`), **Groq** (`OpenAIChatCompletionClient`), and **Local Ollama** (`OpenAIChatClient`).

---

## Project Structure

```text
ContagionIQ/
├── app.py                        # Dark-themed Streamlit + Plotly executive workbench
├── demo.py                       # CLI runner for the 4-agent workflow
├── requirements.txt              # Python dependencies
├── adapters/                     # Pydantic-validated data adapters
│   ├── i360.py                   # Company financials & sector shocks
│   ├── covenant_guard.py         # Bank covenant thresholds & EWS signals
│   ├── data_xmine.py             # Extracted filing documents & supply edges
│   └── model_infinity.py         # Model validation status, limitations & drift metrics
├── agents/
│   ├── tools.py                  # Agent tools (contagion analysis, evidence audit, HITL publish)
│   └── workflow.py               # 4-agent MAF SequentialBuilder workflow & LLM client builders
├── contracts/
│   └── schema.py                 # Pydantic v2 schemas (including ContagionReport)
├── data/
│   ├── i360.json                 # 10 companies across Steel, Auto Components, Auto OEMs, Infrastructure
│   ├── covenant_guard.json       # Covenant & EWS records
│   ├── data_xmine.json           # 10 extracted filings & 10 directed supply edges
│   └── model_infinity.json       # PD_MODEL_2025 & EWS_COVENANT_V3 governance records
├── engine/
│   ├── financials.py             # FinancialStressEngine
│   └── graph.py                  # SupplyChainGraphEngine
├── observability/
│   └── audit.py                  # InvestigationAuditLogger (JSONL telemetry)
└── tests/                        # Pytest suite (14 tests)
    ├── test_app_history.py
    ├── test_contagion_tools.py
    ├── test_demo.py
    ├── test_financial.py
    └── test_observability.py
```

---

## Setup & Configuration

### 1. Install Dependencies
Using the project virtual environment (`..\venv`):
```powershell
..\venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Configure `.env`
Create or update `.env` in the `ContagionIQ` directory for your chosen LLM provider:

* **Google Gemini (Recommended)**
  ```env
  LLM_PROVIDER=gemini
  GEMINI_API_KEY=your_gemini_api_key
  GEMINI_MODEL=gemini-3.1-flash-lite
  ```
  *(Lowercase `gemini_api_key` and `gemini_model` are also supported.)*

* **Groq**
  ```env
  LLM_PROVIDER=groq
  GROQ_API_KEY=your_groq_api_key
  GROQ_MODEL=llama-3.3-70b-versatile
  GROQ_MAX_TOKENS=1024
  ```

* **Local Ollama**
  ```env
  LLM_PROVIDER=local
  LOCAL_LLM_BASE_URL=http://localhost:11434/v1
  LOCAL_LLM_MODEL=llama3.1
  LOCAL_LLM_API_KEY=ollama
  ```

---

## How to Run

### Streamlit Interactive Workbench
```powershell
..\venv\Scripts\streamlit.exe run app.py
```

### CLI Demo
```powershell
# Default coking coal +20% scenario
..\venv\Scripts\python.exe demo.py

# Custom shock scenario
..\venv\Scripts\python.exe demo.py "Iron ore prices surged 15%. Analyze 2-hop contagion from Steel."
```

### Run Test Suite
```powershell
..\venv\Scripts\python.exe -m pytest -v
```

---

## Future Enhancements (Production-Ready & Scalable Roadmap)

The following upgrades are planned post-demo to transition ContagionIQ from a single-user prototype to a production-grade, multi-user platform:

1. **Database & Live Connector Migration**
   * Replace static JSON files loaded at import time (`adapters/`, `agents/tools.py`) with live async connectors backed by **PostgreSQL** (financials, covenants, governance) and **Neo4j** or indexed adjacency tables (supply-chain graph).
   * Migrate `data/published_analyses.json` and `logs/investigation_audit.jsonl` to **PostgreSQL** to eliminate file-write race conditions under concurrent users.

2. **Decoupled Backend API & Async Job Queue**
   * Separate the deterministic engine and 4-agent workflow from Streamlit behind a **FastAPI** service.
   * Offload long-running multi-agent investigations to an async worker queue (**Celery + Redis** or **Temporal**) so the UI remains non-blocking and horizontally scalable.

3. **LLM Reliability, Structured Guardrails & Caching**
   * Add exponential-backoff retries and automatic provider/model fallback (e.g., `gemini-3.1-flash-lite` → `gemini-3.8-flash` → Groq/local) to handle `503` and `429` responses gracefully.
   * Enforce [`ContagionReport`](contracts/schema.py) structured output validation on `ReportSynthesizer`.
   * Cache identical `(shock_pct, primary_sector, max_hops, prompt)` runs in **Redis** to cut latency and token spend.

4. **Engine Performance at Scale (10,000+ Entities)**
   * Vectorize [`FinancialStressEngine`](engine/financials.py) with batch Pandas/Polars operations instead of per-company single-row DataFrames.
   * Aggregate multi-path pass-through shocks at the `company_id` level when a borrower is exposed through multiple upstream suppliers.

5. **Enterprise Security, Observability & CI/CD**
   * Add **SSO / OAuth + RBAC** so only authorized credit analysts can trigger **Approve & Publish**, and move API keys from `.env` into a secret manager (AWS/GCP Secret Manager or HashiCorp Vault).
   * Export [`InvestigationAuditLogger`](observability/audit.py) events, token usage, and latency histograms via **OpenTelemetry** to Grafana/Datadog.
   * Containerize with **Docker** and add a CI/CD pipeline running `pytest`, `ruff`, and `mypy`.
