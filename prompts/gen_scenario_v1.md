You are writing free-form scenario tasks for a memory benchmark. A scenario is an OPEN task (not a question) whose good completion naturally USES 2-3 given memories without mentioning that any memory exists.
Output STRICT JSON only — no prose, no code fences.

User persona: {persona}

Memories to weave in (their SECRET ANSWER WORDS must NOT appear in the scenario text):
{memories}

Task: write ONE open task (40-90 words) addressed to the user's assistant, e.g. "draft a message to my landlord about ...", "plan my Saturday morning ...", "write a short toast for ...". The task must be naturally unsolvable-without-general-knowledge UNLESS the assistant uses the given memories; it must read like a real personal-assistant request, must NOT mention "memory", "you know that", "as I told you", and must NOT contain any answer keyword from the memories.

JSON shape:
{{"text": "..."}}
