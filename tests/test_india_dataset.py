from pathlib import Path

from adapters.covenant_guard import CovenantGuardAdapter
from adapters.data_xmine import DataXMineAdapter
from adapters.i360 import I360Adapter
from adapters.model_infinity import ModelInfinityAdapter
import app


def test_india_public_dataset_schemas_and_dscr_consistency() -> None:
    india_dir = Path(__file__).resolve().parent.parent / "data_india"
    i360 = I360Adapter(data_path=india_dir / "i360.json")
    cg = CovenantGuardAdapter(data_path=india_dir / "covenant_guard.json")
    dx = DataXMineAdapter(data_path=india_dir / "data_xmine.json")
    mi = ModelInfinityAdapter(data_path=india_dir / "model_infinity.json")

    companies = i360.list_companies()
    assert len(companies) == 14
    assert len(cg.list_all()) == 14
    assert len(dx.list_edges()) == 17
    assert len(mi.list_models()) == 2

    i360_ids = {c.company_id for c in companies}
    cg_ids = {r.company_id for r in cg.list_all()}
    doc_ids = {d.doc_id for d in dx.list_documents()}
    edge_doc_ids = {e.evidence_doc_id for e in dx.list_edges()}
    edge_nodes = {e.source_id for e in dx.list_edges()} | {e.target_id for e in dx.list_edges()}

    assert i360_ids == cg_ids
    assert edge_nodes <= i360_ids
    assert edge_doc_ids <= doc_ids

    for c in companies:
        calc_dscr = round(c.ebitda_cr / c.annual_debt_service_cr, 2)
        assert abs(calc_dscr - c.current_dscr) <= 0.02, f"{c.company_id}: {calc_dscr} != {c.current_dscr}"
        cov = cg.get_by_company(c.company_id)
        assert cov is not None and cov.covenants
        assert abs(cov.covenants[0].current_value - c.current_dscr) <= 0.01


def test_app_services_supports_india_dataset() -> None:
    services = app.get_services("india")
    rows = app.compute_full_stress_table(services, shock_pct=20.0, primary_sector="Steel", max_hops=2)
    assert len(rows) == 14
    assert any(r["hop"] == 2 for r in rows)
    fig_net = app.build_contagion_figure(rows, services["xmine"].list_edges(), selected_company_id="AUTO_SUP_B", mode="company")
    fig_bar = app.build_dscr_comparison_figure(rows)
    assert len(fig_net.data) > 0
    assert len(fig_bar.data) == 3
