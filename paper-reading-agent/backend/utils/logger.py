import logging
import json
import time
from pathlib import Path
from backend.config import config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("paper-agent")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    return logger


logger = setup_logging()


class APILogger:
    """Records every LLM API call to outputs/api_log.jsonl."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.output_dir / "api_log.jsonl"

    def log(
        self,
        *,
        timestamp: str,
        model: str,
        messages_count: int,
        tokens_used: int,
        elapsed_ms: int,
        success: bool,
        error: str | None = None,
    ):
        entry = {
            "timestamp": timestamp,
            "model": model,
            "messages_count": messages_count,
            "tokens_used": tokens_used,
            "elapsed_ms": elapsed_ms,
            "success": success,
            "error": error,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


api_logger = APILogger()
