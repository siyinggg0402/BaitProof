"""What the hackathon asks for, kept true: a licence, a short README that says how Token Factory and the NVIDIA models are used, and a description with real links."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
VISION = "nvidia/Nemotron-3.5-Super-VL"
DEMO = "https://baitproof-sy.duckdns.org"
REPO = "https://github.com/siyinggg0402/Is-This-Legit"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_repository_has_an_open_source_licence():
    assert read("LICENSE").startswith("MIT License")


def test_the_readme_says_how_each_requirement_is_met():
    readme = read("README.md")
    assert "## Hackathon requirements" in readme and "## Setup" in readme
    assert "Nebius Token Factory" in readme and MODEL in readme and VISION in readme and "core/ai/llm.py" in readme
    assert "Tavily" in readme and "core/ai/verify.py" in readme and DEMO in readme and "MIT" in readme


def test_the_readme_stays_short():
    assert len(read("README.md").splitlines()) <= 150   # the long measurements live in docs/EVALUATION.md


def test_the_models_named_in_the_readme_are_the_ones_the_code_uses():
    assert MODEL in read(".env.example")
    assert VISION in read("core/ai/llm.py")


def test_the_description_has_real_links_and_the_feedback_section():
    devpost = read("docs/DEVPOST.md")
    assert DEMO in devpost and REPO in devpost and "Feedback on the Nebius and NVIDIA tools" in devpost
    assert "[URL]" not in devpost and "[repo URL]" not in devpost and "[Fill" not in devpost


def test_no_leftover_planning_notes_or_the_old_hosting_in_the_docs():
    for name in ("README.md", "deploy/README.md", "deploy/setup_vm.sh"):
        text = read(name)
        assert "Nebius VM" not in text and "PLAN §" not in text, name


def test_every_file_the_readme_links_to_exists():
    import re

    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", read("README.md")):
        if not target.startswith("http"):
            assert (ROOT / target).exists(), target
