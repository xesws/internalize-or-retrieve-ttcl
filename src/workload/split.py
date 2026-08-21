"""Session-level dev/test split with disjoint personas (proposal §5.5).

Each synthetic user is generated independently (fresh persona call), so
splitting at USER granularity gives persona-disjoint splits by construction;
sessions stay integral within each user (session-level split unit).
"""
from __future__ import annotations

from typing import Any


def split_workload(users: list[dict], dev_user_ids: list[str]) -> tuple[dict, dict]:
    by_id = {u["user_id"]: u for u in users}
    if len(by_id) != len(users):
        raise ValueError("duplicate user ids")
    dev_ids = set(dev_user_ids)
    unknown = dev_ids - set(by_id)
    if unknown:
        raise ValueError(f"dev ids not present: {sorted(unknown)}")
    dev = [by_id[i] for i in sorted(dev_ids)]
    test = [u for u in users if u["user_id"] not in dev_ids]
    if not test:
        raise ValueError("test split is empty")
    return ({"split": "dev", "users": dev},
            {"split": "test", "users": test})


def assert_persona_disjoint(dev: dict, test: dict) -> None:
    dev_ids = {u["user_id"] for u in dev["users"]}
    test_ids = {u["user_id"] for u in test["users"]}
    assert not (dev_ids & test_ids), f"persona overlap: {dev_ids & test_ids}"
    # and no shared memory ids / scenario ids either
    dev_mem = {m["id"] for u in dev["users"] for m in u["memories"]}
    test_mem = {m["id"] for u in test["users"] for m in u["memories"]}
    assert not (dev_mem & test_mem), "memory id overlap across splits"
