# ContagionIQ — Complete New User Guide & UI / Chart Reader

This guide walks any new user step by step through using **ContagionIQ** ([`app.py`](app.py)) and explains every card, chart, badge, and report section in plain English.

---

## Part A: Step-by-Step Guide for a New User

### Step 1: Open the App & Configure the AI Model (Left Sidebar)
1. Launch the dashboard (`..\venv\Scripts\streamlit.exe run app.py`) or open your deployed URL.
2. In the **left sidebar (`AI Model Configuration`)**:
   * **LLM Provider**: Choose **Google Gemini**, **Groq Cloud**, or **Local Ollama**.
   * **Model Name**: Pre-filled with the default model (e.g., `gemini-3.1-flash-lite`), or type another supported model.
   * **API Key (Optional Override)**: Paste your own API key, or leave it blank to use the key already configured in `.env` / Streamlit Secrets.
   * *(If using Local Ollama, you can also set the **Ollama Base URL**; if using Groq, you can adjust **Max Completion Tokens**.)*

### Step 2: Pick a Scenario Preset (or Enter Your Own)
At the top of the main page, either:
* Click one of the **3 Quick Presets** (`Preset: Coking Coal +20% (Steel)`, `Preset: Mild Input +10% (Steel)`, or `Preset: Severe Spike +35% (Steel)`), **OR**
* Type your own scenario in **Price Spike Scenario (What Happened?)**, pick the **Starting Affected Industry** (`Energy & Mining`, `Steel`, `Cement & Materials`, `Auto Components`, `Auto OEMs`, or `Infrastructure`), set **Cost Increase (%)**, and choose **Supply Chain Depth (Steps)** (`1` or `2`).

### Step 3: Click `Run Ripple Impact Analysis`
* The deterministic financial & graph engines immediately recalculate all **14 Indian companies** across **6 sectors**.
* The 4-step AI workflow runs in sequence (`Step 1: Understand the Price Spike` → `Step 2: Calculate Domino Impact` → `Step 3: Spot Data Gaps & Risks` → `Step 4: Write Summary Report`) and writes a telemetry entry to `logs/investigation_audit.jsonl`.

### Step 4: Scan the Executive Summary & Risk Buckets
* Read the **5 KPI cards**, the **Plain-English Summary**, and the **3 Risk Snapshot buckets** (`🔴 At Risk`, `🟡 Watch Closely`, `🟢 Safe`) to see the portfolio impact in 5 seconds.

### Step 5: Explore the Supply Chain Map & Any Company's Story
* Use the **Select Any Company** dropdown to highlight a specific company's upstream suppliers and downstream buyers on the right-hand network chart, then read its **3-Point Story** and **5 detail tabs**.

### Step 6: Review, Export, Approve & Save
* Download the **Stress Matrix (CSV)** or **Report (Markdown)**.
* Click **Approve & Publish to EI Review Queue** (or **Hold / Request Analyst Revision**) to permanently save the analysis in `data/published_analyses.json` so anyone can filter and re-open it later in Section 5.

---

## Part B: How to Read Every Section & Chart

### 1. Top KPI Cards, Plain-English Summary & Risk Buckets

| KPI Card | What It Means in Plain English |
|---|---|
| **Companies Tracked** | Total Indian public companies tracked in the portfolio (`14` across 6 sectors). |
| **At-Risk Companies** | How many companies drop below their bank's minimum loan safety ratio after the price spike. |
| **Loan Exposure at Risk** | Total debt (`₹ Cr`) held by at-risk companies, plus what `%` of total portfolio debt that represents. |
| **Downstream Customers Hit** | Suppliers, builders, and auto makers indirectly hit 1 or 2 steps down the supply chain. |
| **Peak Cash Tied in Bills** | Highest extra cash (`₹ Cr`) tied up in unpaid customer bills if payments slow down. |

Right below the KPIs:
* **Plain-English Summary**: Auto-generated 1-sentence takeaway summarizing how many companies are at risk vs. safe.
* **3 Risk Snapshot Buckets**: Groups every company by name into **🔴 At Risk**, **🟡 Watch Closely**, and **🟢 Safe**.
* **Plain-English Guide: What Do These Terms Mean?**: Collapsible cheat-sheet explaining *DSCR*, *Hop 0/1/2*, *Pass-Through*, *Margin & bps*, and *WC Drag*.

---

### 2. How to Read the Supply Chain Ripple Map (Section 1)

There are **two side-by-side network graphs** showing how a price spike travels from left to right:

* **Columns (Left to Right)**:
  * **Hop 0 (Direct Impact)**: Upstream producers (`Coal India`, `NTPC`, `Tata Steel`, `JSW Steel`).
  * **Hop 1 (Tier-1 Suppliers)**: Auto component makers, cement producers, and EPC contractors (`Bharat Forge`, `Samvardhana Motherson`, `Sundram Fasteners`, `Dilip Buildcon`, `IRB Infrastructure`, `UltraTech Cement`, `Ambuja Cements`).
  * **Hop 2 (OEMs & Metro)**: Downstream auto makers and large EPC (`Maruti Suzuki`, `Tata Motors`, `Larsen & Toubro`).
* **Node Labels & Colors**:
  * Each node shows the company name and a clear status tag: `🔴 AT RISK (<dscr>x)`, `🟡 WATCH (<dscr>x)`, or `🟢 SAFE (<dscr>x)`.
  * Hover over any circle to see full details (Sector, Path, Base vs. Stressed DSCR, Margin change, Cash Tied in Bills).
* **Lines & Edge Labels**:
  * Lines connect supplier → buyer. Labels like `28% (DX-IND-02)` mean the buyer depends on that supplier for `28%` of that input, backed by filing `DX-IND-02`.
  * Hover over any line to read the exact quote and confidence score.
* **Left Chart vs. Right Chart**:
  * **Left (`Full Supply Chain Contagion Network`)**: Shows all 14 companies and 17 supply links; the selected company has a **bright cyan ring**.
  * **Right (`Selected Company Subgraph: <ID>`)**: Highlights **only** the selected company's upstream suppliers and downstream customers in bright cyan, dimming unrelated nodes.

---

### 3. Company Deep-Dive Trace (Section 2)

Select any company from the dropdown to inspect:
* **5 Key Metrics + Plain-English Verdict**: Hop Depth, Base DSCR, Stressed DSCR (with delta), Min Covenant DSCR, and Breach status, followed by a 1-sentence verdict.
* **3-Point Story Card**: Summarizes **Why It's Affected**, **Money Impact**, and **Source Proof** in plain English.
* **5 Detail Tabs**:
  1. **Graph Paths & Pass-Through**: Exact supply paths and pass-through percentages reaching this company.
  2. **i360 & Stress Math**: Exact EBITDA, margin, DSCR, and raw financial inputs.
  3. **Covenant Guard & EWS**: Bank loan thresholds and any active Early Warning Signals.
  4. **Data XMine Evidence**: Extracted annual reports, EPC procurement filings, and confidence scores.
  5. **Model Infinity Governance**: Model validation status (`APPROVED` / `CONDITIONAL`), known limitations, and drift metrics (`PSI`, `Gini`, `KS`).

---

### 4. How to Read the DSCR Bar Chart & Financial Impact Summary (Section 3)

#### Chart: `Loan Safety Ratio: Before vs. After Price Spike`
* **Gray Bar (`Before Price Spike`)**: The company's loan safety ratio *before* the price spike.
* **Red or Green Bar (`After Price Spike`)**: The company's loan safety ratio *after* the price spike (`Red` = At Risk / Breach; `Green` = Safe).
* **Dashed Amber Line (`Bank Safety Minimum`)**: The covenant floor for each company. **Whenever a colored bar sits below the dashed amber line, that company is at risk of missing its bank safety limit.**

#### Financial Impact Summary Table & CSV Export
* Shows all 14 companies with **Safety Margin Left (%)** and **Risk Status** (`🔴 At Risk`, `🟡 Watch`, `🟢 Safe`).
* Click **Download Stress Matrix (CSV)** to export the table.

---

### 5. AI Investigation Report, Sign-Off, History & Telemetry (Sections 4–6)

* **Section 4 — AI Investigation Report & Analyst Sign-Off**:
  * Expand **Inspect Every AI Step** to view outputs from `Step 1: Understand the Price Spike` through `Step 4: Write Summary Report`.
  * Read the **Synthesized Investigation Report** (5 sections: `## Shock Assessment`, `## Affected Companies`, `## Exposure Paths & Evidence`, `## Risk Challenger Flags`, `## Recommended Analyst Actions`) and click **Download Report (Markdown)** to save a copy.
  * Click **Approve & Publish to EI Review Queue** (or **Hold / Request Analyst Revision**) to permanently record the analysis.
* **Section 5 — Past Saved Analyses (Persistent History)**:
  * Displays all saved reports from `data/published_analyses.json` (persists across restarts), filterable by **Status** (`All`, `PUBLISHED`, `HELD`), **Min Shock (%)**, **Date**, and **Keyword / Company**.
* **Section 6 — Observability & Audit Telemetry**:
  * Displays live operational metrics from `logs/investigation_audit.jsonl`: total logged runs, average AI workflow latency, latest Run ID, cited `DX-*` documents, and per-run audit rows.
