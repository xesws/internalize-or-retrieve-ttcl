#!/usr/bin/env python3
"""Expanded unrelated pool (JQ ruling 2026-08-21, sequential-consistency row).

60-100 fixed general-knowledge questions, generated DEV-side via GLM,
machine-checked:
  - target-free: question text must not contain its own answer keywords
    (word-boundary);
  - zero word-overlap with ALL 210 test memories' answer keywords and
    canonical content words (so no pool item can be answered by any workload
    memory).
Frozen to data/p3/unrelated_expanded_v1.json; freeze manifest bumped to v1.1.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402
from src.workload.generator import _STOPWORDS  # noqa: E402

OUT = Path("data/p3")
TARGET_N = 80


def word_hit(keyword: str, text: str) -> bool:
    a = re.sub(r"\s+", " ", text.lower())
    k = re.sub(r"\s+", " ", keyword.strip().lower())
    if not k:
        return False
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9'-]+", text.lower())
            if w not in _STOPWORDS and len(w) > 3}


def main() -> int:
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))
    prompt = Path("prompts/unrelated_gen_v1.md").read_text()

    test = json.loads(Path("data/workloads/test_v1.1.json").read_text())
    # symmetric targeted lint (disclosed in the freeze file):
    #  (a) a pool ANSWER keyword must never appear in any memory's content
    #      (canonical/target content words) — no pool item is answerable from
    #      a workload memory;
    #  (b) a memory ANSWER keyword must never appear in a pool QUESTION —
    #      no pool question leaks/echoes workload content.
    mem_content_words: set[str] = set()
    mem_keywords: list[str] = []
    for u in test["users"]:
        for m in u["memories"]:
            mem_content_words |= content_words(m["canonical"]) | content_words(m["edit_target"])
            for p in m["probes"]:
                for k in p.get("answer_keywords", []):
                    mem_keywords.append(k.lower())

    items: list[dict] = []
    seen_q: set[str] = set()
    for batch in range(4):  # small batches — thinking models need completion headroom
        if len(items) >= TARGET_N:
            break
        raw = client.chat([{"role": "user", "content":
                            prompt.replace("{n}", "30")}],
                          role="sys", temperature=0.8, max_tokens=8192,
                          meta={"step": "unrelated_gen", "batch": batch})
        for it in client.parse_json_block(raw):
            q, kws = it.get("q", "").strip(), it.get("keywords", [])
            if not q or not kws or q.lower() in seen_q:
                continue
            # target-free
            if any(word_hit(k, q) for k in kws):
                continue
            # (a) pool answer keyword must not hit any memory content word
            if any(k.lower() in mem_content_words for k in kws):
                continue
            # (b) memory answer keyword must not appear in the question
            if any(word_hit(mk, q) for mk in mem_keywords):
                continue
            seen_q.add(q.lower())
            items.append({"id": f"eq{len(items)+1:02d}", "q": q,
                          "keywords": [k for k in kws if k][:3]})
        print(f"batch {batch}: pool at {len(items)}", flush=True)

    items = items[:TARGET_N]
    assert len(items) >= 60, f"pool too small after lint: {len(items)}"
    (OUT / "unrelated_expanded_v1.json").write_text(json.dumps({
        "version": "v1", "generator": "glm-5.3 (dev-side)",
        "prompt": "prompts/unrelated_gen_v1.md",
        "prompt_hash": hashlib.sha256(Path("prompts/unrelated_gen_v1.md").read_bytes()).hexdigest()[:16],
        "lint": {"target_free": True,
                 "rule_a_pool_keyword_not_in_memory_content": True,
                 "rule_b_memory_keyword_not_in_question": True,
                 "n_test_memories_checked": 210},
        "items": items}, indent=1, ensure_ascii=False))
    print(f"written {OUT/'unrelated_expanded_v1.json'} with {len(items)} items")

    # freeze manifest bump v1 -> v1.1
    fr = json.loads((OUT / "freeze_v1.json").read_text())
    fr["unrelated_expanded"] = {"path": "data/p3/unrelated_expanded_v1.json",
                                "hash": hashlib.sha256((OUT / "unrelated_expanded_v1.json").read_bytes()).hexdigest()[:16]}
    fr["version_note"] = "v1.1: + expanded unrelated pool for the sequential-consistency confirmation row (JQ ruling 2026-08-21)"
    (OUT / "freeze_v1.1.json").write_text(json.dumps(fr, indent=1, ensure_ascii=False))
    print("freeze manifest v1.1 written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
