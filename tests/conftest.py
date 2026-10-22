import pytest

from core.ai import llm
from core.pipelines.check import tools
from core.obs import logger


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BAITPROOF_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("BAITPROOF_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setitem(logger.DROPPED, "count", 0)
    monkeypatch.setenv("BAITPROOF_CACHE_DIR", str(tmp_path / "cache"))  # never a phishing list left on this machine by a real run
    monkeypatch.setenv("BAITPROOF_NET_TOOLS", "0")  # tests never touch the network; a test opts in and mocks the call
    monkeypatch.setattr(llm, "available", lambda: False)  # tests are offline & deterministic

    def no_network(*_a, **_k):
        raise OSError("the network is closed in tests; a test that needs an answer mocks the tool")
    monkeypatch.setattr(tools, "_http_bytes", no_network)
    tools._cert_cache.clear()
    tools._cert_pause["until"] = 0.0  # every registry/certificate-log/Wikidata call goes through here
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
