"""Workload generator (proposal §5.2): synthetic multi-session users with
typed memory candidates + probe suites, built via the hosted GEN model.

Pipeline per user (each step journaled per item; rerun skips finished items):
  P  persona + typed memory pool + supersede/near-miss pairs   (1 call)
  S  per-session user turns embedding assigned pool items      (n_sessions calls)
  M  per-memory edit fields + 3 QA probes + key prompts        (n_mem calls)
  D  supersede / near-miss pair probes                         (~n_pairs calls)
  E  free-form scenarios bundling 2-3 memories                 (~n_scen calls)

Deterministic parts (assignment of items to sessions, ids, delays, themes)
use random.Random(seed + user_index); LLM steps are generative and the FROZEN
artifact (data/workloads/*.json + hashes) is the reproducibility unit.
"""
from __future__ import annotations

import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.llm import client
from src.workload import lint, schema

PROMPT_VERSION = "v1"

_THEMES = [
    "morning routine", "workday wrap-up", "weekend plans", "family call",
    "health and appointments", "travel arrangements", "home organization",
    "hobby progress", "social plans", "errands and admin", "quiet evening",
    "commute chatter", "meal planning", "reading and media", "money matters",
]

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "my", "me", "i", "you", "your", "it", "its", "at", "by", "with", "from",
}


def answer_keywords(target: str, limit: int = 3) -> list[str]:
    """Mechanically derive probe answer keywords from the edit target."""
    words = [w for w in re.findall(r"[A-Za-z0-9'-]+", target.lower())
             if w not in _STOPWORDS and len(w) > 2]
    words = words[:limit]
    return words or [target.strip().lower()]


def turn_matches(rec: dict) -> bool:
    """turn_text must carry the canonical's content (keyword overlap); used by
    the generator's rebind step and by the freeze gate."""
    def _kw(text: str) -> list[str]:
        return [w for w in re.findall(r"[A-Za-z0-9'-]+", text.lower())
                if w not in _STOPWORDS and len(w) > 2]
    kws = set(_kw(rec["canonical"])) | set(_kw(rec.get("edit_target", "")))
    t = re.sub(r"\s+", " ", rec["turn_text"].lower())
    return any(k in t for k in kws)


class WorkloadGenerator:
    def __init__(
        self,
        user_index: int,
        *,
        run_dir: Path,
        n_sessions: int = 24,
        per_session: tuple[int, int] = (2, 4),
        gen_role: str = "gen",
        seed: int = 42,
        max_workers: int = 6,
    ):
        self.user_id = f"u{user_index:02d}"
        self.rng = random.Random(seed + user_index)
        self.run_dir = Path(run_dir)
        # Journal namespaced by n_sessions: plan_memories shuffles pool items
        # with an rng whose consumption depends on n_sessions, so journals from
        # a different session count MUST NOT be reused (canonical<->id drift).
        self.journal = self.run_dir / f"journal_{self.user_id}_s{n_sessions}"
        self.journal.mkdir(parents=True, exist_ok=True)
        self.n_sessions = n_sessions
        self.per_session = per_session
        self.gen_role = gen_role
        self.max_workers = max_workers
        self._lock = threading.Lock()

    # --- journaling (idempotent resume) -------------------------------------------------
    def _journal_path(self, step: str) -> Path:
        return self.journal / f"{step}.jsonl"

    def _load_journal(self, step: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        p = self._journal_path(step)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    out[rec["key"]] = rec["value"]
        return out

    def _save(self, step: str, key: str, value: Any) -> None:
        with self._lock:
            with self._journal_path(step).open("a") as f:
                f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")

    def _prompt(self, name: str) -> str:
        return (Path(__file__).resolve().parents[2] / "prompts" / name).read_text()

    def _call(self, prompt_text: str, tag: str, temperature: float = 0.8,
              max_tokens: int = 8192) -> Any:
        """One JSON call. Truncated replies (thinking models can spend the
        whole completion budget on reasoning) get ONE retry at double budget."""
        raw = client.chat(
            [{"role": "user", "content": prompt_text}],
            role=self.gen_role, temperature=temperature,
            max_tokens=max_tokens, meta={"step": tag, "user": self.user_id},
        )
        try:
            return client.parse_json_block(raw)
        except client.LLMError:
            raw = client.chat(
                [{"role": "user", "content": prompt_text}],
                role=self.gen_role, temperature=max(temperature, 0.5),
                max_tokens=max_tokens * 2,
                meta={"step": tag + ":retry", "user": self.user_id},
            )
            return client.parse_json_block(raw)

    # --- steps ---------------------------------------------------------------------------
    def step_persona(self) -> dict:
        cached = self._load_journal("persona")
        if cached:
            return cached["persona"]
        persona = self._call(self._prompt("gen_persona_v1.md"), "persona", temperature=0.9)
        self._save("persona", "persona", persona)
        return persona

    def plan_memories(self, persona: dict) -> list[dict]:
        """Deterministic plan: pool items -> session assignments, ids, types."""
        items: list[dict] = []
        mid = 0

        def add(statement: str, mtype: str, session_idx: int, **extra: Any) -> dict:
            nonlocal mid
            mem = {
                "id": f"{self.user_id}-m{mid:03d}",
                "user_id": self.user_id,
                "session_idx": session_idx,
                "canonical": statement,
                "type": mtype,
                **extra,
            }
            items.append(mem)
            mid += 1
            return mem

        all_statements = (
            [(s, "belief") for s in persona["beliefs"]]
            + [(s, "fact") for s in persona["facts"]]
            + [(s, "transient") for s in persona["transients"]]
        )
        self.rng.shuffle(all_statements)

        supersede_new_ids: dict[str, str] = {}
        nearmiss_b_ids: dict[str, str] = {}
        # place paired items first so old lands early, new lands later
        pair_lookup_old: dict[str, tuple[str, str]] = {}
        for old, new in persona.get("supersede_pairs", []):
            pair_lookup_old[old] = (old, new)
        near_lookup_a: dict[str, str] = {}
        for a, b in persona.get("near_miss_pairs", []):
            near_lookup_a[a] = b

        lo, hi = self.per_session
        sessions = list(range(self.n_sessions))
        slots: dict[int, list] = {s: [] for s in sessions}
        # count capacity
        capacity = sum(self.rng.randint(lo, hi) for _ in sessions)
        # reserve slots for supersede-old (early third) and new (5-8 later)
        def pick_session(later_than: int | None = None, before: int | None = None) -> int:
            while True:
                s = self.rng.randrange(self.n_sessions)
                if later_than is not None and s <= later_than + 2:
                    continue
                if before is not None and s >= before:
                    continue
                if len(slots[s]) >= hi:
                    continue
                return s

        for old, new in persona.get("supersede_pairs", []):
            s_old = self.rng.randrange(max(2, self.n_sessions // 3))
            s_new = min(s_old + self.rng.randint(4, 8), self.n_sessions - 1)
            slots[s_old].append((old, "belief_or_fact", {"supersede_pair": (old, new)}))
            slots[s_new].append((new, "belief_or_fact", {"supersede_pair": (old, new), "is_new": True}))
        for a, b in persona.get("near_miss_pairs", []):
            s_a = self.rng.randrange(self.n_sessions)
            s_b = min(s_a + self.rng.randint(1, 5), self.n_sessions - 1)
            slots[s_a].append((a, "belief_or_fact", {"near_miss_pair": (a, b), "is_a": True}))
            slots[s_b].append((b, "belief_or_fact", {"near_miss_pair": (a, b), "is_a": False}))

        # fill remaining slots with shuffled plain statements
        plain = [s for s, t in all_statements
                 if s not in pair_lookup_old and s not in near_lookup_a]
        plain_idx = 0
        for s in sessions:
            while len(slots[s]) < self.rng.randint(lo, hi) and plain_idx < len(plain):
                slots[s].append((plain[plain_idx], None, {}))
                plain_idx += 1
        # leftovers appended to random sessions
        while plain_idx < len(plain):
            s = self.rng.randrange(self.n_sessions)
            slots[s].append((plain[plain_idx], None, {}))
            plain_idx += 1

        type_of = {s: t for s, t in all_statements}
        supersede_ids: dict[str, str] = {}   # old canonical -> old mem id
        nearmiss_ids: dict[str, str] = {}    # a canonical -> a mem id
        for s in sessions:
            for statement, forced_type, extra in slots[s]:
                mtype = (type_of.get(statement, "fact")
                         if forced_type in (None, "belief_or_fact") else forced_type)
                mem = add(statement, mtype, s)
                if "supersede_pair" in extra:
                    old, new = extra["supersede_pair"]
                    if statement == old:
                        supersede_ids[old] = mem["id"]
                    else:
                        mem["pending_supersede_of"] = (old, new)
                if "near_miss_pair" in extra and extra.get("is_a"):
                    nearmiss_ids[statement] = mem["id"]
                if "near_miss_pair" in extra and not extra.get("is_a"):
                    mem["pending_nearmiss_a"] = extra["near_miss_pair"][0]

        for mem in items:
            if "pending_supersede_of" in mem:
                old, _ = mem.pop("pending_supersede_of")
                mem["supersede_of"] = supersede_ids.get(old)
            if "pending_nearmiss_a" in mem:
                a = mem.pop("pending_nearmiss_a")
                mem["near_miss_twin_of"] = nearmiss_ids.get(a)
        return items

    def step_sessions(self, persona: dict, plan: list[dict]) -> dict[int, list[dict]]:
        """Per-session turn texts; returns session_idx -> embedded records."""
        cached = self._load_journal("sessions")
        by_session: dict[int, list[dict]] = {}
        for s in range(self.n_sessions):
            assigned = [m for m in plan if m["session_idx"] == s]
            by_session[s] = assigned
        todo = [s for s in range(self.n_sessions)
                if by_session[s] and str(s) not in cached]
        pool_text = "\n".join(f"- {m['canonical']}" for m in plan)

        def one(s: int) -> None:
            assigned = by_session[s]
            prompt = (self._prompt("gen_sessions_v1.md")
                      .replace("{persona}", persona["persona"])
                      .replace("{pool}", pool_text)
                      .replace("{session_idx}", str(s))
                      .replace("{n_sessions}", str(self.n_sessions))
                      .replace("{theme}", self.rng.choice(_THEMES))
                      .replace("{n_turns}", str(min(8, 3 + len(assigned))))
                      .replace("{assigned}", "\n".join(
                          f"- [{m['id']}] {m['canonical']}" for m in assigned)))
            try:
                recs = self._call(prompt, f"session_{s}")
                got = {r.get("id") for r in recs}
                want = {m["id"] for m in assigned}
                if got != want:
                    raise ValueError(f"incomplete session records: missing={sorted(want - got)} extra={sorted(got - want)}")
                self._save("sessions", str(s), recs)
            except Exception as e:  # noqa: BLE001 — journal the failure, surface at end
                self._save("session_errors", str(s), str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            list(ex.map(one, todo))
        merged = dict(cached)
        for k, v in self._load_journal("sessions").items():
            merged[k] = v
        return {int(k): v for k, v in merged.items()}

    def step_memory_fields(self, persona: dict, plan: list[dict]) -> dict[str, dict]:
        cached = self._load_journal("memory")
        todo = [m for m in plan if m["id"] not in cached]

        def one(m: dict) -> None:
            k = self.rng.randint(3, 8)
            prompt = (self._prompt("gen_memory_v1.md")
                      .replace("{persona}", persona["persona"])
                      .replace("{canonical}", m["canonical"])
                      .replace("{mem_type}", m["type"])
                      .replace("{session_idx}", str(m["session_idx"]))
                      .replace("{n_sessions}", str(self.n_sessions))
                      .replace("{k}", str(k)))
            try:
                rec = self._call(prompt, f"memory_{m['id']}")
                rec["after_sessions"] = k
                self._save("memory", m["id"], rec)
            except Exception as e:  # noqa: BLE001
                self._save("memory_errors", m["id"], str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            list(ex.map(one, todo))
        return {**cached, **self._load_journal("memory")}

    def step_pair_probes(self, persona: dict, plan: list[dict], fields: dict[str, dict]) -> dict[str, dict]:
        """Supersede pairs -> {probe_new, probe_old}; near-miss pairs -> {probe}."""
        cached = self._load_journal("pairs")
        by_id = {m["id"]: m for m in plan}
        by_canonical = {m["canonical"]: m for m in plan}
        jobs: list[tuple[str, str, dict, dict]] = []  # key, kind, old_mem, new_mem

        for m in plan:
            if m.get("supersede_of"):
                old_mem = by_id[m["supersede_of"]]
                key = f"supersede:{m['id']}"
                if key not in cached:
                    jobs.append((key, "supersede", old_mem, m))
            if m.get("near_miss_twin_of"):
                a_mem = by_id[m["near_miss_twin_of"]]
                key = f"nearmiss:{a_mem['id']}"
                if key not in cached:
                    jobs.append((key, "near_miss", a_mem, m))

        def one(job: tuple[str, str, dict, dict]) -> None:
            key, kind, old_mem, new_mem = job
            prompt = (self._prompt("gen_supersede_nearmiss_v1.md")
                      .replace("{kind}", "supersede (new replaced old)" if kind == "supersede"
                               else "near-miss (two similar subjects)")
                      .replace("{old}", old_mem["canonical"])
                      .replace("{new}", new_mem["canonical"])
                      .replace("{old_target}", fields.get(old_mem["id"], {}).get("edit_target", ""))
                      .replace("{new_target}", fields.get(new_mem["id"], {}).get("edit_target", "")))
            try:
                rec = self._call(prompt, key)
                self._save("pairs", key, rec)
            except Exception as e:  # noqa: BLE001
                self._save("pair_errors", key, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            list(ex.map(one, jobs))
        return {**cached, **self._load_journal("pairs")}

    def step_scenarios(self, persona: dict, plan: list[dict], fields: dict[str, dict]) -> list[dict]:
        cached = self._load_journal("scenarios")
        # deterministic scenario grouping: 2-3 durable (belief/fact) memories
        durable = [m for m in plan if m["type"] in ("belief", "fact")
                   and not m.get("supersede_of")]
        groups: list[list[dict]] = []
        i = 0
        n_scen = max(4, len(durable) // 8)
        while i < len(durable) and len(groups) < n_scen:
            size = self.rng.choice([2, 3, 3])
            groups.append(durable[i:i + size])
            i += size
        todo = [(gid, g) for gid, g in enumerate(groups) if f"sc{gid:03d}" not in cached]

        def one(item: tuple[int, list[dict]]) -> None:
            gid, group = item
            memories = "\n".join(
                f"- [{m['id']}] {m['canonical']} (answer words to avoid: "
                f"{', '.join(answer_keywords(fields.get(m['id'], {}).get('edit_target', '')))})"
                for m in group)
            prompt = (self._prompt("gen_scenario_v1.md")
                      .replace("{persona}", persona["persona"])
                      .replace("{memories}", memories))
            try:
                rec = self._call(prompt, f"scenario_sc{gid:03d}")
                rec["id"] = f"{self.user_id}-sc{gid:03d}"
                rec["user_id"] = self.user_id
                rec["memory_ids"] = [m["id"] for m in group]
                self._save("scenarios", f"sc{gid:03d}", rec)
            except Exception as e:  # noqa: BLE001
                self._save("scenario_errors", f"sc{gid:03d}", str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            list(ex.map(one, todo))
        merged = {**cached, **self._load_journal("scenarios")}
        return [v for _, v in sorted(merged.items())]

    # --- assembly ------------------------------------------------------------------------
    def generate(self) -> dict:
        persona = self.step_persona()
        plan = self.plan_memories(persona)
        sessions = self.step_sessions(persona, plan)
        fields = self.step_memory_fields(persona, plan)
        pairs = self.step_pair_probes(persona, plan, fields)
        scenarios = self.step_scenarios(persona, plan, fields)

        scenario_by_memory: dict[str, str] = {}
        for sc in scenarios:
            for mid in sc["memory_ids"]:
                scenario_by_memory[mid] = sc["id"]

        errors = []
        memories: list[dict] = []
        for m in plan:
            f = fields.get(m["id"])
            turn = None
            for rec in sessions.get(m["session_idx"], []):
                if rec.get("id") == m["id"]:
                    turn = rec.get("turn_text")
                    break
            if f is None:
                errors.append({"memory": m["id"], "error": "missing fields"})
                continue
            if not turn:
                errors.append({"memory": m["id"], "error": "missing turn_text"})
                continue
            kws = answer_keywords(f.get("edit_target", ""))
            probes: list[dict] = [
                {"kind": "qa_immediate", "text": f["qa_immediate"], "answer_keywords": kws},
                {"kind": "qa_delayed", "text": f["qa_delayed"], "answer_keywords": kws,
                 "after_sessions": f.get("after_sessions", 5)},
                {"kind": "qa_paraphrase", "text": f["qa_paraphrase"], "answer_keywords": kws},
            ]
            if m["id"] in scenario_by_memory:
                probes.append({"kind": "free_scenario",
                               "scenario_id": scenario_by_memory[m["id"]],
                               "answer_keywords": kws})
            if m.get("supersede_of"):
                pair = pairs.get(f"supersede:{m['id']}", {})
                if pair.get("probe_new"):
                    probes.append({"kind": "supersede_new",
                                   "text": pair["probe_new"],
                                   "answer_keywords": kws})
            if m.get("near_miss_twin_of"):
                # memory B of a near-miss pair: the probe asks A's subject and
                # attaches to A after the loop (see below)
                pass

            rec = {
                "id": m["id"], "user_id": m["user_id"], "session_idx": m["session_idx"],
                "turn_text": turn, "type": m["type"], "canonical": m["canonical"],
                "subject": m["canonical"][:60],
                "edit_stem": f.get("edit_stem", ""), "edit_target": f.get("edit_target", " "),
                "key_prompts": f.get("key_prompts", []), "confidence": 0.9,
                "supersede_of": m.get("supersede_of"),
                "near_miss_twin_of": m.get("near_miss_twin_of"),
                "probes": probes,
            }
            memories.append(rec)

        # OLD memory of each supersede pair: "what did it used to be" probe
        # (asked after the supersede; measures old-value retention/staleness).
        # Memory A of each near-miss pair: probe asking A's subject (B is the
        # collision risk).
        rec_by_id = {r["id"]: r for r in memories}
        for m in plan:
            if m.get("supersede_of") and m["supersede_of"] in rec_by_id:
                pair = pairs.get(f"supersede:{m['id']}", {})
                old_rec = rec_by_id[m["supersede_of"]]
                if pair.get("probe_old"):
                    old_rec["probes"].append({
                        "kind": "supersede_old", "text": pair["probe_old"],
                        "answer_keywords": answer_keywords(old_rec["edit_target"])})
            if m.get("near_miss_twin_of") and m["id"] in rec_by_id:
                # near-miss pair probe is keyed by memory A's id (the subject
                # being asked); m is memory B carrying the twin link
                pair = pairs.get(f"nearmiss:{m['near_miss_twin_of']}", {})
                if pair.get("probe"):
                    a_id = m["near_miss_twin_of"]
                    rec_by_id[a_id]["probes"].append({
                        "kind": "near_miss", "text": pair["probe"],
                        "answer_keywords": answer_keywords(rec_by_id[a_id]["edit_target"]),
                        "near_miss_of": m["id"]})

        # --- consistency audit + rebind --------------------------------------------------
        rebound = 0
        cached_rebind = self._load_journal("rebind")
        for rec in memories:
            if turn_matches(rec):
                continue
            mid = rec["id"]
            new_turn = None
            if mid in cached_rebind:
                new_turn = cached_rebind[mid].get("turn_text")
            else:
                prompt = (self._prompt("gen_rebind_v1.md")
                          .replace("{canonical}", rec["canonical"]))
                try:
                    out = self._call(prompt, f"rebind_{mid}", temperature=0.7)
                    new_turn = out.get("turn_text")
                    self._save("rebind", mid, {"turn_text": new_turn})
                except Exception as e:  # noqa: BLE001
                    self._save("rebind_errors", mid, str(e))
            if new_turn and len(new_turn) >= 8:
                rec["turn_text"] = new_turn
                rec["rebound"] = True
                rebound += 1
        still_mismatched = [r["id"] for r in memories if not turn_matches(r)]

        return {
            "user_id": self.user_id,
            "n_sessions": self.n_sessions,
            "memories": memories,
            "scenarios": scenarios,
            "_errors": errors,
            "_rebound": rebound,
            "_turn_mismatches": still_mismatched,
        }
