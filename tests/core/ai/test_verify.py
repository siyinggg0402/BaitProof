"""The web-search tool offers a company's website only when it looks like the company's own: directories and social sites ranking for its name are not it."""
import sys
from types import SimpleNamespace

import pytest

from core.ai import verify


@pytest.fixture
def search(monkeypatch):
    """A stand-in for the Tavily client that returns the given hostnames, in order, and remembers what it was asked."""
    asked = {}

    def install(*hosts):
        class Client:
            def __init__(self, api_key):
                asked["key"] = api_key

            def search(self, **kw):
                asked.update(kw)
                return {"results": [{"url": f"https://{h}/page"} for h in hosts]}

        monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=Client))
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        return asked
    return install


def test_a_data_broker_ranking_first_is_not_offered_as_the_official_site(search):
    asked = search("leadiq.com", "www.routesonline.com", "www.iata.org", "en.wikipedia.org", "sg.linkedin.com", "www.changiairport.com", "www.jewelchangiairport.com")
    assert verify.official_sites("Changi Airport Group") == ["changiairport.com", "jewelchangiairport.com"]
    assert "leadiq.com" in asked["exclude_domains"] and asked["query"] == "Changi Airport Group official website"


def test_nothing_that_looks_like_the_company_means_no_answer_rather_than_a_guess(search):
    search("mapquest.com", "www.aelitedentalimplant.com", "www.mom.gov.sg", "www.straitstimes.com")
    assert verify.official_sites("Dr Tan Clinic Bukit Timah") == []


def test_best_match_comes_first_and_the_shortest_name_breaks_a_tie(search):
    search("zenithlogisticsinc.com", "straussborrelli.com", "www.zenithlog.com", "zenithlogistics.net")  # two words matched beat one; of two that match both, the shorter name wins
    assert verify.official_sites("Zenith Logistics") == ["zenithlogistics.net", "zenithlogisticsinc.com", "zenithlog.com"]


def test_a_name_with_nothing_to_compare_gets_no_guess(search):
    search("leadiq.com", "www.sfbuy.com", "x.com")
    assert verify.official_sites("顺丰速运") == []


def test_a_failure_is_raised_for_the_tool_gate_to_skip(monkeypatch):
    class Client:
        def __init__(self, api_key):
            pass

        def search(self, **kw):
            raise TimeoutError("slow")

    monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=Client))
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    with pytest.raises(TimeoutError):
        verify.official_sites("Anything Co")
