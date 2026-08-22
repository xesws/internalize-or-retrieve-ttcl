#!/usr/bin/env python3
"""P4 router training (MAC only): logistic regression on interpretable
features from the dual-path labels; pure numpy (no new deps). Saves the
fitted router to data/p4/utility_router_v1.json and prints LOO accuracy.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BELIEF_MARKERS = {"prefer", "prefers", "favorite", "favourite", "always", "never",
                  "believes", "values", "loves", "hates", "habit", "swears"}
FACT_MARKERS = {"on", "at", "every", "each", "appointment", "account", "street",
                "held", "meets", "due", "schedule", "password", "keeper"}
MONTHS = {"january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"}


def features(rec: dict) -> list[float]:
    text = f"{rec['canonical']} {rec['edit_stem']}"
    words = re.findall(r"[a-z0-9'-]+", text.lower())
    content = [w for w in words if len(w) > 2]
    caps = re.findall(r"(?<!^)(?<![.!?]\\s)([A-Z][a-z]+)", rec["canonical"])
    return [
        1.0,  # bias
        float(any(ch.isdigit() for ch in text)),
        float(any(w in MONTHS for w in words)),
        float(len(re.findall(r"\\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\\b", text)) > 0),
        float(len(caps) > 0),
        float(len(content) > 8),
        len(set(content)) / max(len(content), 1),  # lexical diversity
        sum(w in BELIEF_MARKERS for w in words),
        sum(w in FACT_MARKERS for w in words),
        float(rec["type"] == "belief"),
        float(rec["type"] == "transient"),
    ]


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def main() -> int:
    doc = json.loads(Path("results/p4/dualpath_dev.json").read_text())
    recs = doc["records"]
    X = np.array([features(r) for r in recs])
    y = np.array([1.0 if r["label"] == "edit" else 0.0 for r in recs])

    # L2-regularized logistic, plain gradient descent
    w = np.zeros(X.shape[1])
    lr, lam, iters = 0.1, 0.01, 20000
    for _ in range(iters):
        p = sigmoid(X @ w)
        grad = X.T @ (p - y) / len(y) + lam * w
        w -= lr * grad
    acc = float(((sigmoid(X @ w) >= 0.5) == (y == 1.0)).mean())

    # leave-one-out
    loo = 0
    for i in range(len(y)):
        idx = [j for j in range(len(y)) if j != i]
        wv = np.zeros(X.shape[1])
        for _ in range(8000):
            p = sigmoid(X[idx] @ wv)
            wv -= 0.1 * (X[idx].T @ (p - y[idx]) / len(idx) + lam * wv)
        loo += int((sigmoid(X[i] @ wv) >= 0.5) == (y[i] == 1.0))
    loo_acc = loo / len(y)

    # apply to ALL test memories (router never saw test during fitting)
    test = json.loads(Path("data/workloads/test_v1.1.json").read_text())
    routing = {}
    for u in test["users"]:
        for m in u["memories"]:
            rec = {"canonical": m["canonical"], "edit_stem": m["edit_stem"],
                   "type": m["type"]}
            p_edit = float(sigmoid(np.array(features(rec)) @ w))
            routing[m["id"]] = "edit" if p_edit >= 0.5 else "rag"
    out = Path("data/p4")
    out.mkdir(parents=True, exist_ok=True)
    (out / "utility_router_v1.json").write_text(json.dumps({
        "model": "L2 logistic on 11 interpretable features (pure numpy)",
        "lambda_loc": doc["lambda_loc"], "lambda_cpu": doc["lambda_cpu"],
        "train_n": len(recs), "train_acc": round(acc, 3), "loo_acc": round(loo_acc, 3),
        "weights": {name: round(float(v), 3) for name, v in zip(
            ["bias", "has_digit", "has_month", "has_weekday", "has_proper_noun",
             "long", "lex_div", "belief_markers", "fact_markers", "is_belief",
             "is_transient"], w)},
        "test_routing": routing}, indent=1, ensure_ascii=False))

    agree = sum(1 for mid, r in routing.items()
                if (r == "edit") == (next(m["type"] == "belief" for u in test["users"]
                                          for m in u["memories"] if m["id"] == mid)))
    n_edit = sum(1 for r in routing.values() if r == "edit")
    print(json.dumps({"train_acc": round(acc, 3), "loo_acc": round(loo_acc, 3),
                      "test_routed_edit": n_edit, "test_total": len(routing)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
