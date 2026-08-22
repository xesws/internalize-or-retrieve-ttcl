"""Red-line invariants on the default config (handbook §4.2)."""
import yaml


def test_red_lines():
    with open("configs/default.yaml") as f:
        cfg = yaml.safe_load(f)
    assert cfg["run"]["seed"] == 42
    assert cfg["run"]["max_new_tokens"] == 512
    assert cfg["horen"]["locked"] is True
    # gate threshold frozen at the dev-swept value (handbook 4.2 one-shot
    # sweep, 2026-08-21: own 1.0 / false-fire 0.0 at 0.90; see configs comment)
    assert cfg["gate"]["hopfield_key_match_threshold"] == 0.90


def test_model_role_heterogeneity():
    with open("configs/default.yaml") as f:
        cfg = yaml.safe_load(f)
    m = cfg["models"]
    # §5.5 hard rules: judge differs from generator AND from the system LLM family
    assert m["judge_model"] != m["gen_model"]
    assert m["judge_model"] != m["sys_model"]
    # and the judge is not from the same family as gen/sys
    assert m["judge_base_url"] != m["gen_base_url"]
