from __future__ import annotations

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adapters.covenant_guard import CovenantGuardAdapter
from adapters.data_xmine import DataXMineAdapter
from adapters.i360 import I360Adapter
from engine.financials import FinancialStressEngine
from engine.graph import SupplyChainGraphEngine


def test_direct_shock_hand_calculated_case() -> None:
    """
    Hand calculation for STEEL_A (Bharat Blast Steel Ltd):
    - revenue_cr = 2400.0, ebitda_cr = 408.0 -> base_cogs = 1992.0
    - raw_material_share_of_cogs = 0.55 -> raw_material_cost_cr = 1095.6
    - +20% direct shock -> incremental_cost_cr = 1095.6 * 0.20 = 219.12
    - stressed_ebitda_cr = 408.0 - 219.12 = 188.88
    - stressed_margin_pct = (188.88 / 2400.0) * 100 = 7.87%
    - stressed_dscr = round(188.88 / 165.0, 2) = 1.14
    - covenant_min_dscr = 1.30 -> stressed_dscr < 1.30 => covenant_breach = True
    """
    i360 = I360Adapter()
    cov = CovenantGuardAdapter()
    engine = FinancialStressEngine(raw_material_share_of_cogs=0.55)

    company = i360.get_company("STEEL_A")
    assert company is not None

    out = engine.stress_company(
        company=company,
        shock_pct=20.0,
        pass_through_factor=1.0,
        is_direct_shock=True,
        covenant_record=cov.get_by_company("STEEL_A"),
    )

    assert out["stressed_ebitda_cr"] == pytest.approx(188.88, abs=0.01)
    assert out["stressed_margin_pct"] == pytest.approx(7.87, abs=0.01)
    assert out["stressed_dscr"] == pytest.approx(1.14, abs=0.01)
    assert out["covenant_breach"] is True


def test_two_hop_contagion_traversal_and_pass_through() -> None:
    """
    Verifies 2-hop downstream reach from STEEL_A and STEEL_B to OEM_B via AUTO_SUP_B:
    - Hop 1: STEEL_A -> AUTO_SUP_B (dep 0.35 -> cumulative 0.35)
    - Hop 2: STEEL_A -> AUTO_SUP_B -> OEM_B (dep 0.50 -> cumulative 0.35 * 0.50 = 0.175)
    """
    xmine = DataXMineAdapter()
    graph = SupplyChainGraphEngine(xmine.list_edges())

    paths = graph.traverse_exposure(["STEEL_A", "STEEL_B"], max_hops=2)
    oem_b_paths = [p for p in paths if p["company_id"] == "OEM_B" and p["path"] == "STEEL_A -> AUTO_SUP_B -> OEM_B"]

    assert len(oem_b_paths) == 1
    assert oem_b_paths[0]["hop"] == 2
    assert oem_b_paths[0]["cumulative_pass_through"] == pytest.approx(0.175, abs=0.0001)
    assert len(oem_b_paths[0]["evidence"]) == 2


def test_downstream_stress_covenant_breach_on_tight_borrower() -> None:
    """
    AUTO_SUP_B (Kaveri Chassis & Drivetrain) starts with stressed/tight DSCR (1.05)
    and covenant_min_dscr = 1.20; any positive shock should keep covenant_breach = True.
    """
    i360 = I360Adapter()
    cov = CovenantGuardAdapter()
    engine = FinancialStressEngine(raw_material_share_of_cogs=0.55)

    company = i360.get_company("AUTO_SUP_B")
    assert company is not None

    out = engine.stress_company(
        company=company,
        shock_pct=20.0,
        pass_through_factor=0.35,
        is_direct_shock=False,
        covenant_record=cov.get_by_company("AUTO_SUP_B"),
    )

    assert out["effective_shock_pct"] == pytest.approx(7.0, abs=0.01)
    assert out["covenant_breach"] is True