import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    base_url: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/v1")
    auth_token: str = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    model: str = os.getenv("MODEL", "deepseek-v4-pro")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    timeout: int = int(os.getenv("TIMEOUT", "60"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "2"))


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    rewrite_max: int = int(os.getenv("REWRITE_MAX", "2"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    db_path: Path | None = None
    paper_dir: Path | None = None
    report_dir: Path | None = None
    output_dir: Path = Path("./outputs")

    def __post_init__(self):
        self.data_dir = self.data_dir.resolve()
        self.db_path = self.data_dir / "paper-reading.db"
        self.paper_dir = self.data_dir / "papers"
        self.report_dir = self.data_dir / "reports"
        self.output_dir = self.output_dir.resolve()
        for d in [self.data_dir, self.paper_dir, self.report_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)


config = Config()
