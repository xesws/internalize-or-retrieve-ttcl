You are writing general-knowledge quiz questions for a control pool. Each item: one short question whose answer is a single unambiguous word or short phrase (science, geography, history, arts, everyday knowledge). Difficulty: mainstream, answerable by a good assistant WITHOUT any personal context.
Output STRICT JSON only — no prose, no code fences.

Write {n} diverse questions. Each must contain its answer keywords in a separate field. The question text must NOT contain the answer (target-free).

JSON shape:
[{{"id": "eq01", "q": "...", "keywords": ["..."]}}, ...]
