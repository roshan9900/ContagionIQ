from __future__ import annotations

from typing import Any

import pandas as pd

from contracts.schema import CompanyFinancialsRecords, CovenantGuardRecord


class FinancialStressEngine:
    """Deterministic financial stress and covenant sensitivity engine backed by Pandas."""

    def __init__(self, raw_material_share_of_cogs: float = 0.55) -> None:
        if not (0.0 <= raw_material_share_of_cogs <= 1.0):
            raise ValueError("raw_material_share_of_cogs must be between 0.0 and 1.0")
        self.raw_material_share_of_cogs = raw_material_share_of_cogs

    def stress_company(
        self,
        company: CompanyFinancialsRecords,
        shock_pct: float,
        pass_through_factor: float = 1.0,
        is_direct_shock: bool = False,
        covenant_record: CovenantGuardRecord | None = None,
    ) -> dict[str, Any]:
        """
        Computes stressed EBITDA, EBITDA margin, DSCR, covenant breach status,
        and working-capital cash drag for a single company.
        """
        effective_shock_pct = (
            float(shock_pct)
            if is_direct_shock
            else float(shock_pct) * float(pass_through_factor)
        )

        base_cogs = max(0.0, company.revenue_cr - company.ebitda_cr)
        raw_material_cost_cr = base_cogs * self.raw_material_share_of_cogs
        incremental_cost_cr = raw_material_cost_cr * (effective_shock_pct / 100.0)

        stressed_ebitda_cr = max(0.0, company.ebitda_cr - incremental_cost_cr)
        base_margin_pct = (
            (company.ebitda_cr / company.revenue_cr) * 100.0 if company.revenue_cr > 0 else 0.0
        )
        stressed_margin_pct = (
            (stressed_ebitda_cr / company.revenue_cr) * 100.0 if company.revenue_cr > 0 else 0.0
        )

        stressed_dscr = (
            round(stressed_ebitda_cr / company.annual_debt_service_cr, 2)
            if company.annual_debt_service_cr > 0
            else 0.0
        )

        # Working capital stress estimate: higher input costs + slight DSO stretch (+3 days on direct/high shock)
        dso_stretch_days = 3 if effective_shock_pct >= 5.0 else 1
        daily_revenue = company.revenue_cr / 365.0
        wc_receivables_drag_cr = round(daily_revenue * dso_stretch_days, 2)

        covenant_status = "UNKNOWN"
        active_ews_signals: list[str] = []
        if covenant_record is not None:
            dscr_covs = [c for c in covenant_record.covenants if c.metric_type == "DSCR"]
            if dscr_covs:
                covenant_status = dscr_covs[0].status
            active_ews_signals = [
                f"{s.signal_id} ({s.severity}): {s.description}"
                for s in covenant_record.ews_signals
            ]

        covenant_breach = stressed_dscr < company.covenant_min_dscr

        df = pd.DataFrame(
            [
                {
                    "company_id": company.company_id,
                    "company_name": company.company_name,
                    "sector": company.sector,
                    "is_direct_shock": is_direct_shock,
                    "effective_shock_pct": round(effective_shock_pct, 2),
                    "base_ebitda_cr": round(company.ebitda_cr, 2),
                    "stressed_ebitda_cr": round(stressed_ebitda_cr, 2),
                    "base_margin_pct": round(base_margin_pct, 2),
                    "stressed_margin_pct": round(stressed_margin_pct, 2),
                    "margin_change_bps": round((stressed_margin_pct - base_margin_pct) * 100.0, 0),
                    "base_dscr": round(company.current_dscr, 2),
                    "stressed_dscr": stressed_dscr,
                    "covenant_min_dscr": round(company.covenant_min_dscr, 2),
                    "covenant_breach": covenant_breach,
                    "prior_covenant_status": covenant_status,
                    "wc_receivables_drag_cr": wc_receivables_drag_cr,
                    "active_ews_signals": active_ews_signals,
                }
            ]
        )
        return df.iloc[0].to_dict()