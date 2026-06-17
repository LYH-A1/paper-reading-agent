from backend.config import Config, LLMConfig


def test_config_defaults():
    cfg = Config()
    assert cfg.llm.model == "deepseek-v4-pro"
    assert cfg.rewrite_max == 2
    assert cfg.data_dir.name == "data"


def test_llm_config_defaults():
    llm = LLMConfig()
    assert llm.temperature == 0.7
    assert llm.max_retries == 2
