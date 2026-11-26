from pathlib import Path

from observability.audit import InvestigationAuditLogger


def test_investigation_audit_logger_records_and_lists_recent_runs(tmp_path: Path) -> None:
    log_path = tmp_path / "investigation_audit.jsonl"
    logger = InvestigationAuditLogger(log_path=log_path)

    stress_rows = [
        {
            "company_id": "STEEL_A",
            "covenant_breach": True,
            "evidence": [{"doc_id": "i360-SHOCK-FEED"}],
        },
        {
            "company_id": "AUTO_SUP_B",
            "covenant_breach": True,
            "evidence": [{"doc_id": "DX-8871"}],
        },
        {
            "company_id": "OEM_A",
            "covenant_breach": False,
            "evidence": [{"doc_id": "DX-8801"}, {"doc_id": "DX-9002"}],
        },
    ]

    entry1 = logger.record_run(
        prompt="Coking coal 20%",
        shock_pct=20.0,
        max_hops=2,
        stress_rows=stress_rows,
        agent_step_count=4,
        hitl_status="AWAITING_HUMAN_APPROVAL",
        duration_sec=3.456,
        run_id="RUN-TEST0001",
    )
    entry2 = logger.record_run(
        prompt="Iron ore 15%",
        shock_pct=15.0,
        max_hops=1,
        stress_rows=stress_rows[:1],
        agent_step_count=4,
        hitl_status="PUBLISHED",
        duration_sec=2.1,
        run_id="RUN-TEST0002",
    )

    assert entry1["breach_count"] == 2
    assert entry1["breached_companies"] == ["STEEL_A", "AUTO_SUP_B"]
    assert entry1["cited_documents"] == ["DX-8801", "DX-8871", "DX-9002"]
    assert entry1["duration_sec"] == 3.46

    recent = logger.recent_runs(limit=10)
    assert [r["run_id"] for r in recent] == ["RUN-TEST0002", "RUN-TEST0001"]
    assert entry2["hitl_status"] == "PUBLISHED"
