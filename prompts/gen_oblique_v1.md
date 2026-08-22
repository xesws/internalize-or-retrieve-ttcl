You write OBLIQUE assistant-task texts for a memory-gate diagnostic.

An oblique text is an OPEN task (not a yes/no question) that a personal assistant could only do well by using ONE secret memory, but the task text itself contains NO lexical bridge to that memory: none of the secret answer words, none of the distinctive content words, no cafe/brand/date/place names from the memory.

The task must still be ABOUT the same life situation (scheduling around it, drafting a note that depends on it, packing for it, etc.) so a human would see the connection. It must NOT be retrievable by wording overlap.

Output STRICT JSON only — no prose, no code fences.

User id: {user_id}

SECRET memory (do not copy any distinctive word into the task):
type: {mem_type}
canonical: {canonical}
forbidden words: {forbidden}

Write THREE distinct oblique tasks (25–70 words each), second person to the assistant ("help me…", "draft…", "plan…").
JSON shape:
{{"texts": ["...", "...", "..."]}}
