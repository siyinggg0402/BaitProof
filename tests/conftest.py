import pytest

from core.ai import llm


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BAITPROOF_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(llm, "available", lambda: False)  # tests are offline & deterministic
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
