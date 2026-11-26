# ContagionIQ — How to Read the UI & Charts

This guide explains every section, metric, and chart in the Streamlit dashboard ([`app.py`](app.py)) in plain, non-technical language—useful both for your own reference and when walking a manager through a live demo.

---

## 1. Top Banner & Scenario Controls

* **Hero Banner**: Displays the 4-step workflow (`1. Enter Price Shock` → `2. Trace Domino Impact` → `3. AI Risk Review` → `4. Human Approval & History`) and the active LLM badge (e.g., `LLM: Gemini · gemini-3.1-flash-lite`).
* **Quick Scenario Presets**:
  * **Preset: Coking Coal +20% (Steel)** — standard supply-disruption demo.
  * **Preset: Mild Input +10% (Steel)** — smaller cost increase to show fewer at-risk companies.
  * **Preset: Severe Spike +35% (Steel)** — stress test for extreme commodity price spikes.
* **Control Card**:
  * **Price Spike Scenario (What Happened?)**: Natural-language description sent to the 4 AI agents.
  * **Starting Affected Industry**: Starting industry for the financial impact math (defaults to `Steel`).
  * **Cost Increase (%)**: Percentage cost increase used for the calculations.
  * **Supply Chain Depth (Steps)**: `1` (direct customers only) or `2` (customers of customers).
  * **Run Ripple Impact Analysis**: Runs both the financial math and the 4-agent AI review.

---

## 2. Top KPI Cards & Plain-English Summary

| KPI Card | What It Means in Plain English |
|---|---|
| **Companies Tracked** | Total companies tracked in the portfolio (`10`). |
| **At-Risk Companies** | How many companies drop below their bank's minimum loan safety ratio after the price spike. |
| **Loan Exposure at Risk** | Total debt (`₹ Cr`) held by at-risk companies, plus what `%` of the portfolio's total debt that represents. |
| **Downstream Customers Hit** | Suppliers, builders, and auto makers indirectly hit 1 or 2 steps down the supply chain. |
| **Peak Cash Tied in Bills** | Highest extra cash (`₹ Cr`) tied up in unpaid customer bills if payments slow down. |

Right below the KPIs:
* **Plain-English Summary**: Auto-generated 1-sentence takeaway summarizing how many companies are at risk vs. safe.
* **Plain-English Guide: What Do These Terms Mean?**: Collapsible cheat-sheet explaining *DSCR*, *Hop 0/1/2*, *Pass-Through*, *Margin & bps*, and *WC Drag*.

---

## 3. How to Read the Supply Chain Ripple Map (Section 1)

There are **two side-by-side network graphs** showing how a price spike travels from left to right:

* **Columns (Left to Right)**:
  * **Hop 0 (Direct Shock)**: Companies hit immediately by the raw-material price spike (`STEEL_A`, `STEEL_B`).
  * **Hop 1 (Tier-1 Suppliers)**: Direct customers that buy from Hop 0 (`AUTO_SUP_A`, `AUTO_SUP_B`, `AUTO_SUP_C`, `INFRA_A`, `INFRA_B`).
  * **Hop 2 (OEMs & Metro)**: End-customers two steps downstream (`OEM_A`, `OEM_B`, `INFRA_C`).
* **Node Colors (Health Status)**:
  * **Red**: **At Risk** — Loan safety ratio fell below the bank's minimum limit.
  * **Amber**: **Watch Closely** — Not in breach, but already on a watchlist.
  * **Green**: **Safe** — Loan safety ratio stays above the bank's minimum limit.
* **Node Labels & Hover**:
  * Each circle shows the company ID and its post-spike DSCR (e.g., `AUTO_SUP_B / DSCR 0.68`).
  * Hover over any circle to see full details (Sector, Path, Base vs. Stressed DSCR, Margin change, Cash Tied in Bills).
* **Lines & Edge Labels**:
  * Arrows/lines connect supplier → buyer. Labels like `45% (DX-8801)` mean the buyer depends on that supplier for `45%` of that input, backed by filing `DX-8801`.
  * Hover over any line to read the exact quote and confidence score from the filing.

### Left Chart vs. Right Chart
* **Left (`Full Supply Chain Contagion Network`)**: Shows all 10 companies and all supply links at once. The currently selected company is outlined with a **bright cyan ring**.
* **Right (`Selected Company Subgraph: <ID>`)**: Filters the view to highlight **only** the selected company's upstream suppliers and downstream customers (bright cyan lines), dimming unrelated companies into dark gray so you can trace its exact domino chain cleanly.

---

## 4. Company Deep-Dive Trace (Section 2)

Select any company from the dropdown to inspect:
* **5 Key Metrics + Plain-English Verdict**: Shows Hop Depth, Base DSCR, Stressed DSCR (with change delta), Min Covenant DSCR, and Breach status, followed by a 1-sentence verdict (`Safe` vs. `At Risk`).
* **5 Detail Tabs**:
  1. **Graph Paths & Pass-Through**: Exact supply paths and pass-through percentages reaching this company.
  2. **i360 & Stress Math**: Exact EBITDA, margin, DSCR, and raw financial inputs.
  3. **Covenant Guard & EWS**: Bank loan thresholds and any active Early Warning Signals.
  4. **Data XMine Evidence**: Extracted annual reports, credit filings, and confidence scores.
  5. **Model Infinity Governance**: Model validation status (`APPROVED` / `CONDITIONAL`), known limitations, and drift metrics (`PSI`, `Gini`, `KS`).

---

## 5. How to Read the DSCR Bar Chart & Financial Impact Summary (Section 3)

### Chart: `Loan Safety Ratio: Before vs. After Price Spike`
This chart lets anyone spot troubled companies in 2 seconds:
* **Gray Bar (`Before Price Spike`)**: The company's loan safety ratio *before* the price spike.
* **Red or Green Bar (`After Price Spike`)**: The company's loan safety ratio *after* the price spike.
  * **Red bar** = fell below the bank's minimum requirement (**At Risk / Breach**).
  * **Green bar** = stayed above the bank's minimum requirement (**Safe**).
* **Dashed Amber Line (`Bank Safety Minimum`)**: The covenant floor for each company. **Whenever a colored bar sits below the dashed amber line, that company is at risk of missing its bank safety limit.**

### Financial Impact Summary Table & CSV Export
* Lists all 10 companies side by side, including a **Plain-English Status** column (`At Risk (Loan Limit Breached)`, `Watch Closely`, or `Safe`).
* Click **Download Stress Matrix (CSV)** to export the table for Excel or email sharing.

---

## 6. AI Investigation Report, Sign-Off, History & Telemetry (Sections 4–6)

* **Section 4 — AI Investigation Report & Analyst Sign-Off**:
  * Expand **Inspect Every Agent & Workflow Event Trace** to see what each of the 4 AI agents (`shockanalyst`, `exposureinvestigator`, `riskchallenger`, `reportsynthesizer`) produced.
  * Read the **Synthesized Investigation Report** and click **Download Report (Markdown)** to save a copy.
  * Click **Approve & Publish to EI Review Queue** (or **Hold / Request Analyst Revision**) to permanently record the investigation.

### How to Read the 5-Section Synthesized Investigation Report
Every AI report follows a fixed 5-part structure:
1. **`## Shock Assessment`**: Opens with a 2-sentence plain-English takeaway, then explains the commodity price spike and how it travels from Hop 0 to Hop 2.
2. **`## Affected Companies`**: A summary table of all 10 companies with their Hop, Base DSCR, Stressed DSCR, Min Covenant, and Status (`BREACH` vs. `COMPLIANT`). Any row marked `BREACH` has fallen below its bank loan safety minimum.
3. **`## Exposure Paths & Evidence`**: Explains *why* downstream companies are affected by tracing the exact supplier → buyer chain (e.g., `STEEL_A -> AUTO_SUP_B -> OEM_B`) and citing the exact filing IDs (`DX-8801`, `DX-9015`, etc.).
4. **`## Risk Challenger Flags`**: Acts as a built-in "devil's advocate"—highlighting stale filings (e.g., `FY2024`), low-confidence links (`< 0.82` such as `DX-9104`), linear pass-through assumptions, and Model Infinity limitations (`PD_MODEL_2025` >15% shock gap, `EWS_COVENANT_V3` conditional status).
5. **`## Recommended Analyst Actions`**: Concrete next steps for credit/risk teams (e.g., watchlist escalation, covenant waiver review, requesting updated FY2025/FY2026 supplier annexures).

* **Section 5 — Past Saved Analyses (Persistent History)**:
  * Displays all saved reports from `data/published_analyses.json` (persists even after stopping Streamlit).
  * Filter anytime by **Status** (`All`, `PUBLISHED`, `HELD`), **Min Shock (%)**, **Date**, or **Keyword / Company**.
* **Section 6 — Observability & Audit Telemetry**:
  * Displays live operational metrics from `logs/investigation_audit.jsonl`: total logged runs, average AI workflow latency, latest Run ID, cited `DX-*` documents, and per-run audit rows.
