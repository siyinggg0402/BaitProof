"""Phase 0 gate: confirm the real Nemotron model id, base URL and Tavily params.
Usage: python -m scripts.verify_setup [--list]"""
import os
import sys

import core  # noqa: F401  loads .env


def main() -> int:
    from openai import OpenAI

    base, key = os.getenv("NEBIUS_BASE_URL"), os.getenv("NEBIUS_API_KEY")
    if not (base and key):
        print("Set NEBIUS_BASE_URL and NEBIUS_API_KEY in .env first.")
        return 1
    client = OpenAI(base_url=base, api_key=key)
    ids = sorted(m.id for m in client.models.list().data)
    nemo = [i for i in ids if "nemotron" in i.lower()]
    print("Nemotron models on this endpoint:\n  " + "\n  ".join(nemo or ["(none found!)"]))
    if "--list" in sys.argv:
        print("\nAll models:\n  " + "\n  ".join(ids))
    model = os.getenv("NEBIUS_MODEL")
    if model not in ids:
        print(f"\n✗ NEBIUS_MODEL={model!r} is not in /models. Pick one above.")
        return 1
    r = client.chat.completions.create(model=model, max_tokens=20, messages=[{"role": "user", "content": "Say OK."}])
    print(f"\n✓ {model} replied: {r.choices[0].message.content!r}")
    if os.getenv("TAVILY_API_KEY"):
        from tavily import TavilyClient

        res = TavilyClient(api_key=os.environ["TAVILY_API_KEY"]).search(query="is dhl.com legitimate", max_results=1)
        print("✓ Tavily ok:", list(res.keys()))
    else:
        print("(TAVILY_API_KEY not set, skipping)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
