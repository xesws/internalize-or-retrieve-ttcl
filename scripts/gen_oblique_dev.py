#!/usr/bin/env python3
"""Generate oblique (no-lexical-bridge) task texts for every dev belief/fact.

Dev-only diagnostic (JQ 2026-08-22). Not a test-set artifact. Pipeline:
  generate (GLM) -> lexical-bridge lint -> MiniLM top-10 irretrievability
  audit against the full dev belief+fact canonical corpus. Up to 3 retries
  per slot. Idempotent journal under data/gate_geometry/.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402
from src.workload.generator import _STOPWORDS  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = _ROOT / "data/workloads/dev_v1.1.json"
PROMPT = _ROOT / "prompts/gen_oblique_v1.md"
OUT_DIR = _ROOT / "data/gate_geometry"
JOURNAL = OUT_DIR / "oblique_journal.jsonl"
OUT = OUT_DIR / "oblique_dev_v1.json"
UNRELATED = _ROOT / "data/p3/unrelated_expanded_v1.json"
N_PER = 3
MAX_TRIES = 3
TOP_K = 10


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 3}


def forbidden_for(mem: dict) -> set[str]:
    words: set[str] = set()
    for p in mem.get("probes", []):
        for k in p.get("answer_keywords") or []:
            words |= content_words(k)
            words.add(k.strip().lower())
    words |= content_words(mem.get("canonical", ""))
    words |= content_words(mem.get("edit_target", ""))
    tgt = (mem.get("edit_target") or "").strip().lower()
    if len(tgt) > 1:
        words.add(tgt)
    return {w for w in words if len(w) > 1}


def lexical_bridge(text: str, forbidden: set[str]) -> list[str]:
    t = re.sub(r"\s+", " ", text.lower())
    hits = []
    for w in sorted(forbidden):
        if " " in w:
            if w in t:
                hits.append(w)
        elif re.search(rf"\b{re.escape(w)}\b", t):
            hits.append(w)
    return hits


def load_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def audit_top10(query: str, target_id: str, ids: list[str],
                corpus_emb: np.ndarray, embedder) -> tuple[bool, list[str]]:
    q = embedder.encode([query], normalize_embeddings=True)
    sims = (corpus_emb @ q.T).ravel()  # (N,) @ (N,1) wait: corpus (N,D) @ (D,1) -> (N,1)
    order = np.argsort(-sims)[:TOP_K]
    top_ids = [ids[i] for i in order]
    return target_id not in top_ids, top_ids


def generate_one(prompt_tmpl: str, mem: dict, forbidden: set[str]) -> list[str]:
    filled = (prompt_tmpl
              .replace("{user_id}", mem["user_id"])
              .replace("{mem_type}", mem["type"])
              .replace("{canonical}", mem["canonical"])
              .replace("{forbidden}", ", ".join(sorted(forbidden)[:24])))
    raw = client.chat(
        [{"role": "user", "content": filled}],
        role="gen", temperature=0.9, max_tokens=8192,
        meta={"memory": mem["id"], "task": "oblique"},
    )
    data = client.parse_json_block(raw)
    texts = data.get("texts") if isinstance(data, dict) else data
    if not isinstance(texts, list):
        raise client.LLMError(f"bad oblique payload for {mem['id']}")
    return [str(t).strip() for t in texts if str(t).strip()]


def collect_twins(memories: list[dict]) -> list[dict]:
    by_id = {m["id"]: m for m in memories}
    out = []
    for m in memories:
        twin = m.get("near_miss_twin_of")
        if not twin or twin not in by_id:
            continue
        probes = [p for p in m.get("probes", []) if p.get("kind") == "near_miss"]
        if not probes:
            # dev_v1.1 twin links often lack a dedicated near_miss probe
            probes = [p for p in m.get("probes", []) if p.get("kind") == "qa_paraphrase"]
        if not probes:
            continue
        for p in probes:
            out.append({
                "query": p["text"],
                "self_id": m["id"],
                "related_id": twin,
                "kind": "twin",
            })
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client.set_usage_journal(OUT_DIR / "llm_usage.jsonl")
    prompt_tmpl = PROMPT.read_text()
    prompt_hash = hashlib.sha256(prompt_tmpl.encode()).hexdigest()[:16]
    doc = json.loads(WORKLOAD.read_text())
    memories = [m for u in doc["users"] for m in u["memories"]
                if m["type"] in ("belief", "fact")]
    ids = [m["id"] for m in memories]
    canonicals = [m["canonical"] for m in memories]
    done: dict[str, list] = {}
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done.setdefault(rec["memory_id"], []).append(rec)

    print("loading MiniLM…", flush=True)
    embedder = load_embedder()
    corpus_emb = embedder.encode(canonicals, normalize_embeddings=True)

    journal_lock = threading.Lock()
    embed_lock = threading.Lock()
    accepted: list[dict] = []
    n_fail = 0

    def fill_one(mem: dict) -> tuple[list[dict], int]:
        existing = [r for r in done.get(mem["id"], []) if r.get("accepted")]
        if len(existing) >= N_PER:
            return existing[:N_PER], 0
        forbidden = forbidden_for(mem)
        got = list(existing)
        tries = 0
        while len(got) < N_PER and tries < MAX_TRIES:
            tries += 1
            try:
                cands = generate_one(prompt_tmpl, mem, forbidden)
            except Exception as e:
                print(json.dumps({"event": "gen_fail", "memory": mem["id"],
                                  "err": str(e)[:160]}), flush=True)
                continue
            for text in cands:
                if len(got) >= N_PER:
                    break
                bridges = lexical_bridge(text, forbidden)
                with embed_lock:
                    ok_ret, top = audit_top10(
                        text, mem["id"], ids, corpus_emb, embedder)
                rec = {
                    "memory_id": mem["id"], "user_id": mem["user_id"],
                    "type": mem["type"], "text": text,
                    "lexical_hits": bridges, "retrievable": not ok_ret,
                    "top10": top, "accepted": (not bridges) and ok_ret,
                    "group": "oblique",
                }
                with journal_lock:
                    with JOURNAL.open("a") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if rec["accepted"]:
                    got.append(rec)
        miss = N_PER - len(got[:N_PER])
        print(json.dumps({"event": "memory_done", "memory": mem["id"],
                          "accepted": len(got[:N_PER])}), flush=True)
        return got[:N_PER], miss

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(fill_one, m) for m in memories]
        for fut in as_completed(futs):
            got, miss = fut.result()
            accepted.extend(got)
            n_fail += miss

    unrelated = [{"query": it["q"], "related_id": None, "kind": "unrelated",
                  "id": it["id"]} for it in json.loads(UNRELATED.read_text())["items"]]
    twins = collect_twins(memories)
    payload = {
        "disclosure": "dev-only gate-geometry diagnostic; not a test freeze",
        "prompt": "prompts/gen_oblique_v1.md",
        "prompt_hash": prompt_hash,
        "n_memories": len(memories),
        "n_slots_target": N_PER * len(memories),
        "n_oblique_accepted": len(accepted),
        "n_slots_failed": n_fail,
        "audit": {"embedder": "all-MiniLM-L6-v2", "top_k": TOP_K,
                  "corpus": "dev belief+fact canonicals"},
        "oblique": accepted,
        "twins": twins,
        "unrelated": unrelated,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"written": str(OUT), "accepted": len(accepted),
                      "failed_slots": n_fail, "twins": len(twins),
                      "unrelated": len(unrelated)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
