from backend.app.audit import AuditLogger


def test_audit_logger_appends_json_lines(tmp_path) -> None:
    log_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(str(log_path))

    logger.log({"incident_id": "one", "result": "ok"})
    logger.log({"incident_id": "two", "result": "review"})

    records = logger.read_all()
    assert [record["incident_id"] for record in records] == ["one", "two"]
