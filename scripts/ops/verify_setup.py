"""Phase 0 gate: confirm the real Nemotron model id, base URL and Tavily params.
Usage: python -m scripts.ops.verify_setup [--list]
Never prints the API key. If NEBIUS_BASE_URL is blank it tries Nebius's known endpoints and tells you which one works."""
import os
import sys

import core  # noqa: F401  loads .env

CANDIDATES = ["https://api.tokenfactory.nebius.com/v1/", "https://api.studio.nebius.com/v1/"]  # both are nebius.com hosts only


def find_client(key: str):
    from openai import OpenAI

    bases = [os.environ["NEBIUS_BASE_URL"]] if os.getenv("NEBIUS_BASE_URL") else CANDIDATES
    for base in bases:
        try:
            client = OpenAI(base_url=base, api_key=key, timeout=40, max_retries=1)
            ids = sorted(m.id for m in client.models.list().data)
            return client, base, ids
        except Exception as e:  # report the reason, never the key
            status = getattr(e, "status_code", None)
            hint = {401: " (key rejected: check NEBIUS_API_KEY in .env)", 403: " (key lacks access)", 404: " (wrong base URL path)"}.get(status, "")
            print(f"  ✗ {base}: {type(e).__name__}{f' {status}' if status else ''}: {str(e)[:140]}{hint}")
    return None, None, []


def main() -> int:
    key = os.getenv("NEBIUS_API_KEY")
    if not key:
        print("Set NEBIUS_API_KEY in .env first.")
        return 1
    client, base, ids = find_client(key)
    if not client:
        print("\nNo endpoint accepted the key. Check network/VPN, the key, and the base URL in the Nebius docs.")
        return 1
    print(f"✓ endpoint works. Put this in .env:  NEBIUS_BASE_URL={base}")
    nemo = [i for i in ids if "nemotron" in i.lower()]
    print("\nNemotron models on this endpoint:\n  " + "\n  ".join(nemo or ["(none found!)"]))
    if "--list" in sys.argv:
        print("\nAll models:\n  " + "\n  ".join(ids))
    model = os.getenv("NEBIUS_MODEL")
    if not model:
        print("\nNow set NEBIUS_MODEL (and NEBIUS_MODEL_LIGHT) in .env to one of the Nemotron ids above, preferring the smallest.")
        return 0
    if model not in ids:
        print(f"\n✗ NEBIUS_MODEL={model!r} is not in /models. Pick one above.")
        return 1
    r = client.chat.completions.create(model=model, max_tokens=20, messages=[{"role": "user", "content": "Say OK."}])
    print(f"\n✓ {model} replied: {r.choices[0].message.content!r}  (tokens used: {r.usage.total_tokens if r.usage else '?'})")
    if os.getenv("TAVILY_API_KEY"):
        from tavily import TavilyClient

        res = TavilyClient(api_key=os.environ["TAVILY_API_KEY"]).search(query="is dhl.com legitimate", max_results=1)
        print("✓ Tavily ok:", list(res.keys()))
    else:
        print("(TAVILY_API_KEY not set, skipping)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
