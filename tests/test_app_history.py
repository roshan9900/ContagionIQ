from pathlib import Path

import app


def test_save_load_and_filter_persistent_analyses(tmp_path: Path) -> None:
    history_file = tmp_path / "published_analyses.json"

    app.save_analysis_record(
        {
            "analysis_id": "AN-1",
            "saved_at": "2026-11-25 12:00:00",
            "saved_date": "2026-11-25",
            "status": "PUBLISHED",
            "prompt": "Coking coal prices increased by 20%",
            "shock_pct": 20.0,
            "max_hops": 2,
            "breach_count": 7,
            "breached_companies": ["STEEL_A (Bharat Blast Steel Ltd)"],
            "final_report": "## Shock Assessment\nSteel breach.",
        },
        history_path=history_file,
    )
    app.save_analysis_record(
        {
            "analysis_id": "AN-2",
            "saved_at": "2026-11-24 10:00:00",
            "saved_date": "2026-11-24",
            "status": "HELD",
            "prompt": "Iron ore prices increased by 10%",
            "shock_pct": 10.0,
            "max_hops": 1,
            "breach_count": 2,
            "breached_companies": ["AUTO_SUP_B (Kaveri Chassis & Drivetrain)"],
            "final_report": "## Shock Assessment\nMinor impact.",
        },
        history_path=history_file,
    )

    loaded = app.load_analysis_records(history_path=history_file)
    assert len(loaded) == 2
    assert loaded[0]["analysis_id"] == "AN-2"

    published = app.filter_analysis_records(loaded, status_filter="PUBLISHED")
    assert [r["analysis_id"] for r in published] == ["AN-1"]

    high_shock = app.filter_analysis_records(loaded, min_shock_pct=15.0)
    assert [r["analysis_id"] for r in high_shock] == ["AN-1"]

    by_date = app.filter_analysis_records(loaded, date_filter="2026-11-24")
    assert [r["analysis_id"] for r in by_date] == ["AN-2"]

    by_query = app.filter_analysis_records(loaded, search_query="kaveri")
    assert [r["analysis_id"] for r in by_query] == ["AN-2"]


def test_dscr_comparison_figure_and_provider_label(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("gemini_model", "gemini-3.1-flash-lite")
    assert app._get_active_provider_label() == "LLM: Gemini · gemini-3.1-flash-lite"

    services = app.get_services()
    rows = app.compute_full_stress_table(services, shock_pct=20.0, primary_sector="Steel", max_hops=2)
    fig = app.build_dscr_comparison_figure(rows)
    assert len(fig.data) == 3
    assert len(fig.data[0].x) == 10
