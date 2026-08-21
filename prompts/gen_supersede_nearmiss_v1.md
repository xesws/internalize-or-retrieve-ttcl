You are writing supersede / near-miss probes for a memory benchmark. Supersede = a newer memory replaced an older one about the same subject. Near-miss = two similar-sounding memories about different subjects.
Output STRICT JSON only — no prose, no code fences.

Pair kind: {kind}
Old memory: {old}
New memory: {new}
Old target (SECRET — must not appear in any probe): {old_target}
New target (SECRET — must not appear in any probe): {new_target}

Task:
- supersede: write TWO questions about the subject: "probe_new" = a plain question whose CURRENT correct answer is the new value; "probe_old" = a question asking what the value USED TO BE before the change (correct answer: the old value). Neither may contain either target.
- near_miss: write ONE question that unambiguously asks about the FIRST memory's subject (not the second's), same surface style. It must not contain either target.

JSON shape: {{"probe_new": "...", "probe_old": "..."}} for supersede; {{"probe": "..."}} for near-miss.
