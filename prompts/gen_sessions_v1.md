You are writing one session of a synthetic user's conversation stream for a memory benchmark.
Output STRICT JSON only — no prose, no code fences.

Context — user persona:
{persona}

Known memory pool (you may only surface items from this pool in this session; do not invent new facts):
{pool}

Session index: {session_idx} of {n_sessions} total. Session theme: {theme}.

Task: write {n_turns} natural user turns (single speaker, short messages as if to a personal assistant). Embed the following memory items into the turns as natural first-person statements, in the given order but spread across turns:
{assigned}

Each embedded statement must sound like something a person would actually say (not a database row). Add 1-2 neutral filler turns that carry NO memory content.

JSON shape — one entry per EMBEDDED memory (skip fillers):
[{"turn_idx": 0, "turn_text": "...", "canonical": "<canonical statement from pool, verbatim>", "confidence": 0.95},
 ...]
turn_idx = index of the turn (0-based) in the session where the statement appears.
