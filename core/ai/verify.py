"""Tavily enrichment. Optional: verdicts must work without it."""
from __future__ import annotations

import os
import re

# Directories, data brokers, social networks and encyclopaedias rank for a company's name without being its website: never offered as "the official site".
NOT_OFFICIAL = ("leadiq.com", "zoominfo.com", "rocketreach.co", "apollo.io", "crunchbase.com", "dnb.com", "opencorporates.com", "cbinsights.com", "pitchbook.com",
                "sgpbusiness.com", "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "youtube.com", "reddit.com", "wikipedia.org",
                "wikidata.org", "glassdoor.com", "indeed.com", "yelp.com", "mapquest.com", "tripadvisor.com", "yellowpages.com", "manta.com", "bloomberg.com")
_GENERIC = frozenset("the and for pte ltd limited inc llc company corp group sdn bhd berhad singapore malaysia official website online services service".split())


def _not_official(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in NOT_OFFICIAL)


def _name_match(host: str, words: list[str]) -> int:
    """How many of the company's distinctive words appear in the host's own name (0: it does not look like that company's website)."""
    name = re.sub(r"[^a-z0-9]", "", "".join(label for label in host.split(".")[:-1] if label != "www"))
    return sum(w in name for w in words)


def enrich(domains: list[str], limit: int = 2) -> list[str]:
    if not os.getenv("TAVILY_API_KEY") or not domains:
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        notes = []
        for d in domains[:limit]:
            r = client.search(query=f"is {d} a scam or legitimate website", max_results=3)
            for item in r.get("results", [])[:2]:
                notes.append(f"{d}: {item.get('title', '')} - {str(item.get('content', ''))[:200]}")
        return notes
    except Exception:
        return []


def official_sites(org: str, limit: int = 5) -> list[str]:
    """Hostnames from the top web results for '<org> official website' that look like the company's own site: directories and social networks are left out, and
    so are hosts that do not contain the company's words, best match first (no words to compare means no answer). A weak signal (search ranking is not
    authority), so callers weigh it lightly. Raises on any failure: the tool gate turns that into a skipped tool."""
    from urllib.parse import urlparse

    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    r = client.search(query=f"{org} official website", max_results=limit + 5, exclude_domains=list(NOT_OFFICIAL))
    hosts = []
    for item in r.get("results", []):
        h = (urlparse(item.get("url", "")).hostname or "").lower().removeprefix("www.")
        if h and not _not_official(h):
            hosts.append(h)
    hosts = list(dict.fromkeys(hosts))
    words = [w for w in re.findall(r"[a-z0-9]+", org.lower()) if len(w) >= 3 and w not in _GENERIC]
    if not words:  # a name with nothing we can compare (Chinese, say): search ranking alone is not worth offering
        return []
    return sorted((h for h in hosts if _name_match(h, words)), key=lambda h: (-_name_match(h, words), len(h)))[:limit]
