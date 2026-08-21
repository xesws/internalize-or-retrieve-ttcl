#!/usr/bin/env python3
"""CLI driver for workload generation (Mac only; hosted GEN API, no GPU).

usage:
  python scripts/gen_workload.py --pilot          # 1 user, 6 sessions (E2E check)
  python scripts/gen_workload.py --full           # 2 dev + 4 test users
Reruns resume from the per-user journals (results/workload_build/)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402
from src.manifest import write_manifest  # noqa: E402
from src.workload import freeze as freeze_mod  # noqa: E402
from src.workload.generator import WorkloadGenerator  # noqa: E402

RUN_DIR = Path("results/workload_build")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--sessions", type=int, default=None)
    ap.add_argument("--dev-users", type=int, default=2)
    ap.add_argument("--test-users", type=int, default=4)
    args = ap.parse_args()
    if not (args.pilot or args.full):
        ap.error("choose --pilot or --full")

    client.set_usage_journal(RUN_DIR / "llm_usage.jsonl")
    env = client.load_env()
    gen_model = env.get("GEN_MODEL", "glm-5.3")

    if args.pilot:
        users_spec = [(1, args.sessions or 6)]
    else:
        users_spec = [(i, args.sessions or 24) for i in
                      range(1, args.dev_users + args.test_users + 1)]

    users = []
    failed_users = []
    for idx, n_sessions in users_spec:
        print(f"== generating user u{idx:02d} ({n_sessions} sessions) ==", flush=True)
        gen = WorkloadGenerator(idx, run_dir=RUN_DIR, n_sessions=n_sessions)
        try:
            user = gen.generate()
        except Exception as e:  # noqa: BLE001 — one user's failure must not kill the run
            print(f"   USER FAILED u{idx:02d}: {e}", flush=True)
            failed_users.append({"user": f"u{idx:02d}", "error": str(e)[:300]})
            continue
        if user.get("_errors"):
            print(json.dumps({"user": user["user_id"], "errors": user["_errors"][:5]}, ensure_ascii=False))
        users.append({k: v for k, v in user.items() if k != "_errors"})
        print(f"   memories={len(user['memories'])} scenarios={len(user['scenarios'])} "
              f"errors={len(user.get('_errors', []))}", flush=True)
    if failed_users:
        print(json.dumps({"failed_users": failed_users}, ensure_ascii=False), flush=True)

    if args.pilot:
        # pilot: validate + lint, run the single repair round, report
        from src.workload import lint, repair, schema
        doc = {"version": "pilot", "split": "dev", "users": users}
        pre = lint.workload_leak_report(doc)
        rep = repair.repair_round(users)
        errs = [schema.validate_memory(m) for u in users for m in u["memories"]]
        n_err = sum(len(e) for e in errs)
        post = lint.workload_leak_report(doc)
        print(json.dumps({
            "pilot": True, "users": len(users),
            "memories": sum(len(u["memories"]) for u in users),
            "schema_errors": n_err,
            "lint_pre": {k: pre[k] for k in ("probes", "violations", "rate", "by_kind")},
            "repair": rep,
            "lint_post": {k: post[k] for k in ("probes", "violations", "rate", "by_kind")},
            "usage": client.usage_summary(),
        }, indent=2, ensure_ascii=False))
        return 0 if n_err == 0 and post["rate"] <= repair.LEAK_RATE_STOP else 1

    dev_ids = [f"u{i:02d}" for i in range(1, args.dev_users + 1)]
    from src.workload import repair
    rep = repair.repair_round(users)
    print(json.dumps({"repair": rep}, ensure_ascii=False), flush=True)
    if rep["stop_condition"]:
        print("STOP: leak rate still > 2% after one repair round — reporting, not freezing", flush=True)
        return 2
    report = freeze_mod.freeze(users, dev_ids, generator_model=gen_model)
    write_manifest(RUN_DIR, {
        "run_id": "workload_build",
        "generator_model": gen_model,
        "prompt_hashes": freeze_mod.prompt_hashes(),
        "paid_api_usage": client.usage_summary(),
        "freeze": report,
    })
    print(json.dumps(report["splits"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
