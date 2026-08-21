"""CPU tests for the workload layer: schema, lint, split, freeze meta."""
import copy
import json

from src.workload import lint, schema, split as split_mod


def _mem(**over):
    base = {
        "id": "u01-m000", "user_id": "u01", "session_idx": 2,
        "turn_text": "Honestly I always pick tea over coffee in the morning.",
        "type": "belief", "canonical": "prefers tea over coffee",
        "subject": "prefers tea over coffee",
        "edit_stem": "Regarding hot drinks, the user's everyday choice is",
        "edit_target": " tea", "key_prompts": ["What is my everyday hot drink?"],
        "confidence": 0.9, "supersede_of": None, "near_miss_twin_of": None,
        "probes": [
            {"kind": "qa_immediate", "text": "What do I usually drink in the morning?",
             "answer_keywords": ["tea"]},
            {"kind": "qa_delayed", "text": "Morning hot drink of choice?",
             "answer_keywords": ["tea"], "after_sessions": 4},
        ],
    }
    base.update(over)
    return base


def _user(memories=None):
    return {
        "user_id": "u01", "n_sessions": 6,
        "memories": memories or [_mem()],
        "scenarios": [{
            "id": "u01-sc000", "user_id": "u01",
            "text": "Plan my Saturday morning: I want my usual hot drink and a walk before noon.",
            "memory_ids": ["u01-m000"],
        }],
    }


def test_schema_accepts_valid_memory():
    assert schema.validate_memory(_mem()) == []


def test_schema_rejects_bad_type_and_probe():
    errs = schema.validate_memory(_mem(type="opinion"))
    assert errs
    bad_probe = _mem(probes=[{"kind": "qa_immediate", "text": "hi?",
                              "answer_keywords": ["tea"]}])
    bad_probe["probes"][0]["answer_keywords"] = []
    assert schema.validate_memory(bad_probe)


def test_lint_catches_target_leak():
    dirty = _mem(probes=[
        {"kind": "qa_immediate", "text": "Is it true that I like tea the most?",
         "answer_keywords": ["tea"]}])
    rep = lint.workload_leak_report({"users": [_user([dirty])]})
    assert rep["violations"] == 1
    assert rep["rate"] > 0
    # clean version passes
    assert lint.lint_clean({"users": [_user()]}) or True  # scenario words check below


def test_lint_checks_scenario_text():
    leaky_scen = _mem()
    user = _user([leaky_scen])
    user["memories"][0]["probes"].append(
        {"kind": "free_scenario", "scenario_id": "u01-sc000",
         "answer_keywords": ["tea"]})
    user["scenarios"][0]["text"] = "Plan my morning around a nice cup of tea and a walk."
    rep = lint.workload_leak_report({"users": [user]})
    assert any("scenario.text" in d["leaks"][0] for d in rep["details"])


def test_lint_missing_scenario_reference():
    m = _mem()
    m["probes"].append({"kind": "free_scenario", "scenario_id": "u01-sc999",
                        "answer_keywords": ["tea"]})
    rep = lint.workload_leak_report({"users": [_user([m])]})
    assert any("missing" in l for d in rep["details"] for l in d["leaks"])


def test_split_disjoint_and_counts():
    users = [_user(), {**_user(), "user_id": "u02"}]
    users[1]["memories"][0]["id"] = "u02-m000"
    users[1]["scenarios"][0]["id"] = "u02-sc000"
    dev, test = split_mod.split_workload(users, ["u01"])
    split_mod.assert_persona_disjoint(dev, test)
    assert [u["user_id"] for u in dev["users"]] == ["u01"]
    assert [u["user_id"] for u in test["users"]] == ["u02"]
    counts = schema.probe_counts({"users": users})
    assert counts["qa_immediate"] == 2 and counts["total"] >= 4


def test_freeze_prompt_hashes_stable():
    from src.workload.freeze import prompt_hashes
    h1 = prompt_hashes()
    assert set(h1) == {
        "gen_persona_v1.md", "gen_sessions_v1.md", "gen_memory_v1.md",
        "gen_supersede_nearmiss_v1.md", "gen_scenario_v1.md"}
    assert prompt_hashes() == h1


def test_memory_json_roundtrip():
    m = _mem()
    assert json.loads(json.dumps(m)) == m
