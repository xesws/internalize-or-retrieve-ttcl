"""Workload schemas (proposal §5.2): memory candidates with hidden type
labels, probe suites, scenarios, pressure knobs. Validated with jsonschema;
the generator may never emit an invalid record (G1: schema 100%)."""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

MEMORY_TYPES = ("belief", "fact", "transient")
PROBE_KINDS = (
    "qa_immediate",      # same-session QA
    "qa_delayed",        # QA k sessions after the memory was written
    "qa_paraphrase",     # reworded QA
    "free_scenario",     # open task text bundling 2-3 memories (target-free)
    "supersede_old",     # after a supersede: probe the OUTDATED value
    "supersede_new",     # after a supersede: probe the NEW value
    "near_miss",         # twin probe: same surface, other ownership
)

MEMORY_SCHEMA: dict[str, Any] = {
    "$defs": {
        "probe": {
            "type": "object",
            "required": ["kind", "answer_keywords"],
            "properties": {
                "kind": {"enum": list(PROBE_KINDS)},
                "text": {"type": "string", "minLength": 4},
                "answer_keywords": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string", "minLength": 2},
                },
                # free_scenario probes reference the scenario instead of text
                "scenario_id": {"type": "string"},
                "after_sessions": {"type": "integer", "minimum": 1},
                "near_miss_of": {"type": "string"},
            },
            "anyOf": [
                {"required": ["text"]},
                {"required": ["scenario_id"]},
            ],
        },
    },
    "type": "object",
    "required": ["id", "user_id", "session_idx", "turn_text", "type", "canonical",
                 "edit_stem", "edit_target", "key_prompts", "confidence", "probes"],
    "properties": {
        "id": {"type": "string", "pattern": "^u\\d+-m\\d+$"},
        "user_id": {"type": "string", "pattern": "^u\\d+$"},
        "session_idx": {"type": "integer", "minimum": 0},
        "turn_text": {"type": "string", "minLength": 8},
        "type": {"enum": list(MEMORY_TYPES)},
        "canonical": {"type": "string", "minLength": 6},
        "subject": {"type": "string"},
        "edit_stem": {"type": "string", "minLength": 6},
        "edit_target": {"type": "string", "minLength": 1},
        "key_prompts": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "supersede_of": {"type": ["string", "null"]},
        "near_miss_twin_of": {"type": ["string", "null"]},
        "probes": {"type": "array", "items": {"$ref": "#/$defs/probe"}},
    },
}

SCENARIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "user_id", "text", "memory_ids"],
    "properties": {
        "id": {"type": "string", "pattern": "^u\\d+-sc\\d+$"},
        "user_id": {"type": "string"},
        "text": {"type": "string", "minLength": 40},
        "memory_ids": {"type": "array", "minItems": 2, "maxItems": 3,
                       "items": {"type": "string"}},
    },
}

# NOTE: the workload-level schema deliberately does NOT embed MEMORY_SCHEMA.
# MEMORY_SCHEMA's internal `$ref: "#/$defs/probe"` resolves against its own
# root; embedding it under WORKLOAD_SCHEMA would repoint the reference at the
# outer document (PointerToNowhere). Memories/scenarios are validated
# item-by-item via validate_memory / validate_scenario instead.
WORKLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["version", "split", "users"],
    "properties": {
        "version": {"type": "string"},
        "split": {"enum": ["dev", "test"]},
        "generator_model": {"type": "string"},
        "prompt_version": {"type": "string"},
        "users": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["user_id", "n_sessions", "memories", "scenarios"],
                "properties": {
                    "user_id": {"type": "string"},
                    "n_sessions": {"type": "integer", "minimum": 1},
                    "memories": {"type": "array"},
                    "scenarios": {"type": "array"},
                },
            },
        },
    },
}

_memory_validator = Draft202012Validator(MEMORY_SCHEMA)
_scenario_validator = Draft202012Validator(SCENARIO_SCHEMA)
_workload_validator = Draft202012Validator(WORKLOAD_SCHEMA)


def validate_memory(record: dict) -> list[str]:
    return [e.message for e in sorted(_memory_validator.iter_errors(record), key=str)]


def validate_scenario(record: dict) -> list[str]:
    return [e.message for e in sorted(_scenario_validator.iter_errors(record), key=str)]


def validate_workload(doc: dict) -> list[str]:
    return [e.message for e in sorted(_workload_validator.iter_errors(doc), key=str)]


def probe_counts(doc: dict) -> dict[str, int]:
    """Probe tallies by kind across all users (G1: probe 计数达标)."""
    counts: dict[str, int] = {k: 0 for k in PROBE_KINDS}
    for user in doc.get("users", []):
        for mem in user.get("memories", []):
            for probe in mem.get("probes", []):
                counts[probe["kind"]] = counts.get(probe["kind"], 0) + 1
    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return counts


def memory_type_counts(doc: dict) -> dict[str, int]:
    counts = {t: 0 for t in MEMORY_TYPES}
    for user in doc.get("users", []):
        for mem in user.get("memories", []):
            counts[mem["type"]] += 1
    counts["total"] = sum(counts.values())
    return counts
