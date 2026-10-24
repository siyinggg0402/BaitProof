import pytest

from core.ai import llm
from core.pipelines.check import tools
from core.obs import logger


REAL_WHOIS_RAW = tools._whois_raw  # the suite closes WHOIS below; a test of its own input checks can still reach the real function


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
    monkeypatch.setattr(tools, "_whois_raw", no_network)  # WHOIS (port 43) is a network call too
    tools._whois_servers.clear()
    tools._cert_cache.clear()
    tools._cert_pause["until"] = 0.0  # every registry/certificate-log/Wikidata call goes through here
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)  # a developer's own push keys (in .env) must not change what a test sees
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)  # (likewise the bot name in .env: a test that wants the one-tap link sets it)
