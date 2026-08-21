"""P2 selection: N=20 stratified from the dev split (workload spec §3).

Rules (frozen): belief >= 6; at least one COMPLETE supersede chain (old+new
both selected); at least one near-miss pair (A+B both selected); remainder by
frozen type ratio; single-user stream preferred for session coherence.
Deterministic under seed=42.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

BELIEF_MIN = 6
N_TOTAL = 20


def select_p2(workload: dict, *, seed: int = 42, n: int = N_TOTAL,
              user_id: str | None = None) -> dict:
    users = workload["users"]
    if user_id:
        users = [u for u in users if u["user_id"] == user_id]
    mems = [m for u in users for m in u["memories"]]

    def chains_in(sel: list[dict]) -> int:
        ids = {m["id"] for m in sel}
        return sum(1 for m in sel if m.get("supersede_of") in ids)

    def nearmiss_pairs_in(sel: list[dict]) -> int:
        ids = {m["id"] for m in sel}
        return sum(1 for m in sel if m.get("near_miss_twin_of") in ids)

    rng = random.Random(seed)
    best: list[dict] | None = None
    # try the single-user pools first (coherent persona), then merged
    pools: list[list[dict]] = [ [m for m in mems if m["user_id"] == u["user_id"]]
                                for u in users ] + [mems]
    for pool in pools:
        beliefs = [m for m in pool if m["type"] == "belief" and not m.get("supersede_of")]
        facts = [m for m in pool if m["type"] == "fact" and not m.get("supersede_of")]
        transients = [m for m in pool if m["type"] == "transient"]
        chain_news = [m for m in pool if m.get("supersede_of")]
        chain_olds = {m["supersede_of"]: next((o for o in pool if o["id"] == m["supersede_of"]), None)
                      for m in chain_news}
        nm_bs = [m for m in pool if m.get("near_miss_twin_of")]
        if len(beliefs) + len(facts) + len(transients) + 2 * len(chain_news) + 2 * len(nm_bs) < n:
            continue
        sel: list[dict] = []
        # 1) one complete supersede chain
        if chain_news:
            cn = rng.choice(chain_news)
            old = chain_olds.get(cn["supersede_of"])
            if old:
                sel += [old, cn]
        # 2) one near-miss pair (A + B)
        for b in rng.sample(nm_bs, k=min(1, len(nm_bs))):
            a = next((o for o in pool if o["id"] == b["near_miss_twin_of"]), None)
            if a:
                sel += [a, b]
        # 3) beliefs up to BELIEF_MIN (minus any already selected)
        have = lambda t: sum(1 for m in sel if m["type"] == t)  # noqa: E731
        need_belief = max(0, BELIEF_MIN - have("belief"))
        sel += rng.sample([m for m in beliefs if m not in sel], k=min(need_belief, len(beliefs)))
        # 4) remainder by frozen ratio (belief:fact:transient ~= 23:62:15) over the rest
        rest = n - len(sel)
        want = {"belief": round(rest * 0.23), "fact": round(rest * 0.62),
                "transient": rest - round(rest * 0.23) - round(rest * 0.62)}
        for t, k in want.items():
            avail = [m for m in {"belief": beliefs, "fact": facts,
                                 "transient": transients}[t] if m not in sel]
            sel += rng.sample(avail, k=min(k, len(avail)))
        # top up from anything left
        leftover = [m for m in beliefs + facts + transients + chain_news if m not in sel]
        rng.shuffle(leftover)
        while len(sel) < n and leftover:
            sel.append(leftover.pop())

        ok = (len(sel) == n and sum(1 for m in sel if m["type"] == "belief") >= BELIEF_MIN
              and chains_in(sel) >= 1 and nearmiss_pairs_in(sel) >= 1)
        if ok:
            best = sel
            break
    if best is None:
        raise ValueError("no pool satisfies the P2 selection constraints")
    best.sort(key=lambda m: (m["session_idx"], m["id"]))
    return {
        "n": len(best),
        "user_id": "+".join(sorted({m["user_id"] for m in best})),
        "counts": {t: sum(1 for m in best if m["type"] == t)
                   for t in ("belief", "fact", "transient")},
        "chains": chains_in(best),
        "near_miss_pairs": nearmiss_pairs_in(best),
        "memory_ids": [m["id"] for m in best],
        "memories": best,
        # scenarios need >= 1 selected memory (partial overlap OK); probes are
        # scored per selected memory inside the scenario
        "scenarios": [sc for u in users for sc in u["scenarios"]
                      if any(mid in {m["id"] for m in best} for mid in sc["memory_ids"])],
    }


def load_dev(path: str | Path = "data/workloads/dev_v1.1.json") -> dict:
    return __import__("json").loads(Path(path).read_text())
