You are preparing one memory of a synthetic user for an editing benchmark: derive its edit fields and QA probes.
Output STRICT JSON only — no prose, no code fences.

User persona (for consistent phrasing):
{persona}

Memory statement (canonical): {canonical}
Type: {mem_type}
Written in session {session_idx} of {n_sessions}.

Produce:
1. edit_stem: a declarative template whose completion is this fact, phrased about "the user" (third person), ending so the target naturally completes it. E.g. canonical "prefers tea over coffee" -> stem "Regarding hot drinks, the user's everyday choice is" target " tea".
2. edit_target: the short completion (1-4 words, leading space, no punctuation).
3. key_prompts: 2 short first-person question forms asking about this fact ("What is my ...?", "Which ... do I ...?"). They must NOT contain the target.
4. qa_immediate: question asked in the SAME session, natural wording.
5. qa_delayed: differently worded question asked {k} sessions later.
6. qa_paraphrase: casual third wording.

HARD RULES:
- NONE of the questions or key_prompts may contain edit_target or its content words (target-free discipline).
- Every question must be answerable by edit_target.
- Never use the phrases "you told me", "as I said", "my memory", "earlier".

JSON shape:
{{"edit_stem": "...", "edit_target": " ...", "key_prompts": ["...", "..."],
  "qa_immediate": "...", "qa_delayed": "...", "qa_paraphrase": "..."}}
