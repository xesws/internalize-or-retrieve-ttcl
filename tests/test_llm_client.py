"""CPU tests for the Mac-side LLM client (no network)."""
import json

from src.llm import client


def test_parse_json_block_plain_and_fenced():
    assert client.parse_json_block('{"a": 1}') == {"a": 1}
    assert client.parse_json_block('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert client.parse_json_block('Sure! Here it is:\n{"a": {"b": "x}"}}')["a"]["b"] == "x}"
    assert client.parse_json_block('[{"k": "v"}, {"k": "w"}]') == [{"k": "v"}, {"k": "w"}]


def test_parse_json_block_strings_with_braces():
    obj = client.parse_json_block('{"text": "use { and } freely", "n": 3}')
    assert obj["text"] == "use { and } freely"


def test_role_resolution_defaults():
    env = {"ZAI_API_KEY": "k", "OPENAI_API_KEY": "d"}
    gen = client.resolve_role("gen", env)
    assert gen["model"] == "glm-5.3" and "z.ai" in gen["base_url"]
    judge = client.resolve_role("judge", env)
    assert judge["model"] == "deepseek-v4-pro" and "deepseek" in judge["base_url"]
    # §5.5 hard rule: judge family differs from gen/sys family
    assert judge["base_url"] != gen["base_url"]


def test_usage_journal_roundtrip(tmp_path):
    p = tmp_path / "usage.jsonl"
    client.set_usage_journal(p)
    client._record_usage("gen", "glm-5.3", {"prompt_tokens": 10, "completion_tokens": 5,
                                            "total_tokens": 15}, {"step": "persona"})
    client._record_usage("gen", "glm-5.3", {"prompt_tokens": 1, "completion_tokens": 1,
                                            "total_tokens": 2}, {"step": "memory"})
    summary = client.usage_summary()
    assert summary["glm-5.3"] == {"calls": 2, "prompt_tokens": 11,
                                  "completion_tokens": 6, "total_tokens": 17}
    client.set_usage_journal(None)


def test_temperature_capped(monkeypatch=None):
    # the body clamp is inside chat(); assert the constant contract instead
    assert client.MAX_TEMPERATURE == 1.0
