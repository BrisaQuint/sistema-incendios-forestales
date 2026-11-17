import logging
import pytest
from sistema_incendios_forestales.operational_logging import configure_logging


def test_rotation_and_secret_canaries(tmp_path):
    handler = configure_logging({"FIREWATCH_LOG_PATH": str(tmp_path / "test.log"),
                                 "FIREWATCH_LOG_MAX_BYTES": "180", "FIREWATCH_LOG_BACKUP_COUNT": "2"})
    try:
        for _ in range(30):
            try:
                raise ValueError("CANARY_HIDDEN_REASONING")
            except ValueError:
                record = logging.LogRecord("uvicorn.error", logging.ERROR, "", 0,
                                           "CANARY_KEY %s", ("CANARY_PROMPT",), __import__('sys').exc_info())
                handler.handle(record)
        files = list(tmp_path.glob("test.log*"))
        assert len(files) == 3
        assert all(path.stat().st_size <= 180 for path in files)
        output = "".join(path.read_text() for path in files)
        assert "CANARY" not in output
        assert "ERROR server diagnostic" in output
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


@pytest.mark.parametrize("key", ["FIREWATCH_LOG_MAX_BYTES", "FIREWATCH_LOG_BACKUP_COUNT"])
def test_invalid_log_limits_fail_without_echoing_values(key):
    with pytest.raises(ValueError) as error:
        configure_logging({key: "CANARY_SECRET"})
    assert "CANARY" not in str(error.value)
