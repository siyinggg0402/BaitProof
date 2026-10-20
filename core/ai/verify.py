"""Tavily enrichment. Optional: verdicts must work without it (PLAN §6a)."""
from __future__ import annotations

import os


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
    """Hostnames of the top web results for '<org> official website'. A weak signal (search ranking is not authority),
    so callers weigh it lightly. Raises on any failure: the tool gate turns that into a skipped tool."""
    from urllib.parse import urlparse

    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    r = client.search(query=f"{org} official website", max_results=limit)
    hosts = []
    for item in r.get("results", []):
        h = (urlparse(item.get("url", "")).hostname or "").lower().removeprefix("www.")
        if h:
            hosts.append(h)
    return list(dict.fromkeys(hosts))
