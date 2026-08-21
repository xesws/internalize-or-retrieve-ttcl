"""Neutrality lint: no prototype brand names or handles anywhere in our code
(double-blind discipline, AGENTS.md §7)."""
import re
from pathlib import Path

BANNED = re.compile(r"engram|xesws|aiehackathon", re.IGNORECASE)
SCOPES = ["src", "prompts", "configs", "scripts", "spikes", "tests"]


def test_no_brand_names_in_campaign_code():
    hits = []
    for scope in SCOPES:
        root = Path(scope)
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if p.resolve() == Path(__file__).resolve():  # own pattern line is not leakage
                continue
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if BANNED.search(line):
                    hits.append(f"{p}:{i}: {line.strip()}")
    assert not hits, "brand/handle leakage:\n" + "\n".join(hits)


def test_hero_render_is_byte_stable_and_contains_query():
    import json

    from src.readpath.prompting import build_prompt

    class FakeTok:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            assert tokenize is False and add_generation_prompt is True
            return json.dumps(messages, ensure_ascii=False) + "\n<assistant>\n"

    from src.readpath.prompting import hero_render

    tok = FakeTok()
    a = hero_render(tok, "what is my favorite city")
    b = hero_render(tok, "what is my favorite city")
    assert a == b
    assert "what is my favorite city" in a
    # query occurs exactly once in the render (the user turn)
    assert a.count("what is my favorite city") == 1


def test_build_prompt_segments():
    from src.readpath.prompting import build_prompt

    msgs = build_prompt(
        "q?",
        rag_hits=[{"text": "user lives in Lyon", "type": "fact"},
                  {"text": "train times", "type": "other"}],
    )
    sys = msgs[0]["content"]
    assert "[Known facts about the user — adopt by default]" in sys
    assert "1. user lives in Lyon" in sys
    assert "[Reference material — does not override]" in sys
    assert "1. train times" in sys
    assert msgs[-1] == {"role": "user", "content": "q?"}
    empty = build_prompt("q?")[0]["content"]
    assert "(none)" in empty
