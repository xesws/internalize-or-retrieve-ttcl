#!/usr/bin/env python3
"""Sequential-consistency confirmation row (JQ ruling 2026-08-21).

POD ONLY. For arms S2 (all-internalize) and S5 (router), per test user:
replay the stream and at cumulative-edit checkpoints {10, 25, end-of-stream}
evaluate the FROZEN expanded unrelated pool (data/p3/unrelated_expanded_v1.json,
75 items). Plus one base-model spot-check of the same pool. Positioning: a
reproduction confirmation consistent with HoReN's published sequential
stability — NOT a threshold comparison, NOT merged into any composite.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import torch
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.manifest import build_manifest, write_manifest  # noqa: E402
from src.readpath import keying  # noqa: E402
from src.readpath.prompting import build_prompt  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

MAX_NEW_TOKENS = 512
CHECKPOINTS = (10, 25)
DEST = {"belief": "edit", "fact": "rag", "transient": "drop"}


def _word_hit(keyword, answer):
    a = re.sub(r"\s+", " ", answer.lower())
    k = re.sub(r"\s+", " ", keyword.strip().lower())
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def gen(model, tok, q):
    messages = build_prompt(q)
    rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(rendered, return_tensors="pt").to("cuda")
    adapter = model_host.edit_module() if model_host.edit_active() else None
    if adapter is not None:
        adapter.query_span = keying.query_span_in_rendered(tok, rendered, q)
    try:
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
    finally:
        if adapter is not None:
            adapter.query_span = None
    ids = out[0][enc["input_ids"].shape[1]:]
    return tok.decode(ids, skip_special_tokens=True), int(ids.shape[0])


def eval_pool(model, tok, pool, journal, done, tag):
    hits = 0
    for it in pool:
        key = f"{tag}|{it['id']}"
        if key in done:
            hits += done[key]
            continue
        ans, n = gen(model, tok, it["q"])
        h = int(any(_word_hit(k, ans) for k in it["keywords"]))
        done[key] = h
        hits += h
        with journal.open("a") as f:
            f.write(json.dumps({"key": key, "q": it["q"], "answer_head": ans[:100],
                                "hit": h, "n_gen": n}) + "\n")
    return hits, len(pool)


def main() -> int:
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    pool = json.loads((_REPO_ROOT / "data" / "p3" / "unrelated_expanded_v1.json").read_text())["items"]
    test = json.loads((_REPO_ROOT / "data" / "workloads" / "test_v1.1.json").read_text())
    s5 = json.loads((_REPO_ROOT / "data" / "p3" / "router_s5_test_v1.json").read_text())["routing"]
    results = {}

    for arm in ("S2", "S5"):
        for user in test["users"]:
            run_dir = _REPO_ROOT / "results" / f"seqcheck_{arm}_{user['user_id']}"
            (run_dir / "logs").mkdir(parents=True, exist_ok=True)
            journal = run_dir / "items.jsonl"
            done: dict[str, int] = {}
            if journal.exists():
                for l in journal.read_text().splitlines():
                    if l.strip():
                        r = json.loads(l)
                        done[r["key"]] = r["hit"]
            model_host.load_base()
            tok = model_host.tokenizer()
            model = model_host.current_model()
            mems = sorted(user["memories"], key=lambda m: (m["session_idx"], m["id"]))
            n_edits = 0
            pending = {c: False for c in CHECKPOINTS}
            per_ck = {}
            for m in mems:
                dest = "edit" if arm == "S2" else DEST[s5.get(m["id"], m["type"])]
                if dest == "edit":
                    editing.edit(model_host.current_model(), {
                        "prompt": m["edit_stem"], "target_new": m["edit_target"],
                        "key_prompts": m["key_prompts"]})
                    model = model_host.current_model()
                    n_edits += 1
                    for c in CHECKPOINTS:
                        if not pending[c] and n_edits >= c:
                            h, n = eval_pool(model, tok, pool, journal, done, f"{arm}|{user['user_id']}|ck{c}")
                            per_ck[f"ck{c}_edits{n_edits}"] = round(h / n, 3)
                            pending[c] = True
            h, n = eval_pool(model, tok, pool, journal, done,
                             f"{arm}|{user['user_id']}|end")
            per_ck[f"end_edits{n_edits}"] = round(h / n, 3)
            results[f"{arm}_{user['user_id']}"] = {"checkpoints": per_ck, "n_edits_total": n_edits}
            write_manifest(run_dir, build_manifest(f"seqcheck_{arm}_{user['user_id']}", cfg, extra={
                "arm": arm, "user_id": user["user_id"], "n_edits": n_edits,
                "pool_size": len(pool)}))
            print(json.dumps({"event": "seqcheck_done", "arm": arm,
                              "user": user["user_id"], "checkpoints": per_ck}), flush=True)

    # base capability spot-check (once, unedited)
    run_dir = _REPO_ROOT / "results" / "seqcheck_BASE"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    journal = run_dir / "items.jsonl"
    done = {}
    if journal.exists():
        for l in journal.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                done[r["key"]] = r["hit"]
    model_host.load_base()
    tok = model_host.tokenizer()
    h, n = eval_pool(model_host.current_model(), tok, pool, journal, done, "BASE")
    results["BASE"] = {"hit_rate": round(h / n, 3), "n": n}
    print(json.dumps({"event": "base_done", "hit_rate": round(h / n, 3)}), flush=True)

    out = _REPO_ROOT / "results" / "seqcheck_summary.json"
    out.write_text(json.dumps({
        "positioning": "reproduction confirmation of HoReN sequential stability; "
                       "not a threshold comparison; not merged into composites",
        "gate_threshold": cfg["gate"]["hopfield_key_match_threshold"],
        "pool": f"{len(pool)} items (frozen v1)",
        "results": results}, indent=1, ensure_ascii=False))
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
