import pytest

from core.ai import llm
from core.obs import logger


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BAITPROOF_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("BAITPROOF_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setitem(logger.DROPPED, "count", 0)
    monkeypatch.setattr(llm, "available", lambda: False)  # tests are offline & deterministic
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
