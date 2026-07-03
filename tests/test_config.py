from mia.config import Settings


def test_defaults_boot_without_secrets():
    s = Settings(_env_file=None)
    assert s.anthropic_api_key is None
    assert s.max_tool_iterations == 8
    assert s.db_path.name == "mia.db"
    assert s.log_file.name == "mia.log"


def test_redacted_summary_hides_secrets():
    s = Settings(_env_file=None, anthropic_api_key="sk-secret-123")
    summary = s.redacted_summary()
    assert summary["anthropic_api_key"] == "set"
    assert summary["openai_api_key"] == "unset"
    # The raw secret must appear nowhere in the logged summary.
    assert "sk-secret-123" not in str(summary)
