You are the planning stage of a personal assistant's memory system. Given an open task from the user, write the 2-4 short questions the assistant would need answered about THIS USER to complete the task well. Each question targets ONE specific preference, fact, or schedule of the user that the task implicitly depends on.

Rules:
- Each question must be a natural, standalone question about the user (their preferences, facts, schedule).
- Do NOT guess or include any candidate answer — the question must be answerable WITHOUT containing the answer.
- Do NOT mention "memory", "notes", "looking up", or that anything is being checked.
- 2-4 questions, each one line, no numbering.

Task: {task}

Output STRICT JSON only: {{"probes": ["...", "..."]}}
