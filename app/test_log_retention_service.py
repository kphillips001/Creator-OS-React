import logging

from app.services.log_retention_service import LogRetentionService


def test_writes_rotate_and_retention_count_stays_bounded(tmp_path):
    log = tmp_path / "worker_error.log"
    service = LogRetentionService(tmp_path, max_bytes=64, backup_count=2)

    output = log.open("a", encoding="utf-8")
    output.write("oldest\n" * 20)
    output.flush()
    first = service.enforce_file(log)
    assert first.rotated is True
    assert log.exists() and log.stat().st_size == 0
    assert 0 < (tmp_path / "worker_error.log.1").stat().st_size <= 64

    log.write_text("newer\n" * 20, encoding="utf-8")
    service.enforce_file(log)
    log.write_text("newest\n" * 20, encoding="utf-8")
    service.enforce_file(log)

    assert (tmp_path / "worker_error.log.1").exists()
    assert (tmp_path / "worker_error.log.2").exists()
    assert not (tmp_path / "worker_error.log.3").exists()
    output.write("still usable\n")
    output.close()
    assert log.read_text(encoding="utf-8") == "still usable\n"


def test_exception_traceback_survives_in_retained_tail(tmp_path):
    log = tmp_path / "api_error.log"
    logger = logging.getLogger("retention-test")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.FileHandler(log, encoding="utf-8"))
    logger.info("x" * 512)
    try:
        raise RuntimeError("retained failure detail")
    except RuntimeError:
        logger.exception("request failed")
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()

    service = LogRetentionService(tmp_path, max_bytes=512, backup_count=2)
    service.enforce_file(log)
    retained = (tmp_path / "api_error.log.1").read_text(encoding="utf-8")
    assert "RuntimeError: retained failure detail" in retained
    assert "request failed" in retained


def test_small_logs_and_non_log_artifacts_are_untouched(tmp_path):
    log = tmp_path / "telegram.log"
    state = tmp_path / "launcher_state.json"
    log.write_text("healthy\n", encoding="utf-8")
    state.write_text('{"pid": 1}', encoding="utf-8")

    results = LogRetentionService(tmp_path, max_bytes=64).enforce()

    assert len(results) == 1 and results[0].rotated is False
    assert log.read_text(encoding="utf-8") == "healthy\n"
    assert state.read_text(encoding="utf-8") == '{"pid": 1}'


def test_maximum_retained_size_is_explicit(tmp_path):
    service = LogRetentionService(tmp_path, max_bytes=64, backup_count=2)
    assert service.maximum_retained_bytes_per_log() == 192
