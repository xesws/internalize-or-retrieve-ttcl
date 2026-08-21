You are the memory router of a personal assistant. For each candidate memory, decide its storage: "belief" (durable preference/stance/habit with no mutable external referent — belongs in long-term internal memory), "fact" (reference info with a concrete updatable referent: dates, places, names, accounts, schedules — belongs in a retrievable store), or "transient" (one-off state/mood/context — discard).
Output STRICT JSON only — no prose, no code fences.

Memory: {memory}

JSON shape: {{"type": "belief"|"fact"|"transient"}}
