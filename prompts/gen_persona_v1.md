You are building a synthetic-user memory workload for a research benchmark.
Output STRICT JSON only — no prose, no code fences.

Task: invent ONE fictional user persona and their memory pool.

Requirements:
- persona: 2 sentences, first person implied third-person sketch (age band, occupation, one life circumstance). Fictional; no real famous people.
- beliefs: 10-14 statements about this user's durable preferences/values/habits (e.g. "prefers tea over coffee", "believes early morning is the best time to write"). These should be STABLE across sessions and phrased so they could surface in ANY relevant generation, not just when asked.
- facts: 10-14 reference facts/schedules about the user's world (e.g. "dentist appointment on the 14th", "train to Lyon on Fridays", "wifi password is river-stone-77"). Updatable, possibly expiring, only needed when asked.
- transients: 6-9 one-off states/moods/contexts (e.g. "tired today", "waiting for a delivery").
- supersede_pairs: 4-6 pairs [old, new] where new later REPLACES old (e.g. old favorite café -> new favorite café after they moved). Pick pairs from beliefs/facts or invent consistent ones; both sides must be same-subject.
- near_miss_pairs: 3-5 pairs [a, b] of statements with SIMILAR surface wording but DIFFERENT subjects (e.g. "favorite city to visit" vs "favorite city to live in") — designed to test key collision.

JSON shape:
{"persona": "...", "beliefs": ["...", ...], "facts": ["...", ...], "transients": ["...", ...],
 "supersede_pairs": [["old", "new"], ...], "near_miss_pairs": [["a", "b"], ...]}
