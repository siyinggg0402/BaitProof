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
