import torch


def parent_module(model, pname):
    components = pname.split(".")
    parent = model
    for component in components[:-1]:
        if hasattr(parent, component):
            parent = getattr(parent, component)
        elif component.isdigit():
            parent = parent[int(component)]
        else:
            raise RuntimeError(f"Couldn't find child module {component}")
    if not hasattr(parent, components[-1]):
        raise RuntimeError(f"Couldn't find child module {components[-1]}")
    return parent


def brackets_to_periods(name):
    return name.replace("[", ".").replace("]", "")


def _tokenize_prompt_and_label(prompt, label, tokenizer, device):
    if not isinstance(prompt, list):
        prompt = [prompt]
    if not isinstance(label, list):
        label = [label]

    mask_token = -100
    full_prompt = [f"{p} {l}" for p, l in zip(prompt, label)]
    # PATCH (ttcl §4.1, 2026-08-21): count prompt tokens from attention_mask.
    # Upstream counted `input_ids != pad_token_id`; Llama tokenizers alias pad
    # to eos, so a prompt encoding ending in a real eos was under-counted by 1
    # (prompt-length off-by-one -> the mask boundary landed on the first target
    # token instead of the last prompt token).
    prompt_enc = tokenizer(list(prompt), return_tensors="pt", padding=True, truncation=True)
    num_prompt_toks = prompt_enc["attention_mask"].sum(dim=1).tolist()

    # PATCH (ttcl §4.1, 2026-08-21): APPEND the terminating eos to the target
    # span. Raw-text encodings carry no eos, so without this the editor trains
    # with no stop signal at all (runaway generation at decode).
    tokens = tokenizer(full_prompt, return_tensors=None, padding=False, truncation=True)
    eos_id = tokenizer.eos_token_id
    pad_id = tokenizer.pad_token_id
    if eos_id is None:
        eos_id = pad_id
    rows = [torch.tensor(list(row) + [eos_id], dtype=torch.long)
            for row in tokens["input_ids"]]
    maxlen = max(r.shape[0] for r in rows)
    input_ids = torch.full((len(rows), maxlen), pad_id if pad_id is not None else eos_id, dtype=torch.long)
    attention = torch.zeros((len(rows), maxlen), dtype=torch.long)
    for i, r in enumerate(rows):
        input_ids[i, : r.shape[0]] = r
        attention[i, : r.shape[0]] = 1
    labels = input_ids.clone()
    for i in range(len(prompt)):
        labels[i][: num_prompt_toks[i]] = mask_token
    # PATCH (ttcl §4.1, 2026-08-21): mask ONLY true padding (attention_mask == 0).
    # Upstream masked `input_ids == pad_token_id`, which — under the pad=eos
    # alias — also erased the target-final eos from the training labels. A real
    # eos inside the supervised target span must stay supervised (the appended
    # eos above is exactly such a token).
    labels[attention == 0] = mask_token

    return {
        "input_ids": input_ids.to(device),
        "attention_mask": attention.to(device),
        "labels": labels.to(device),
    }


def tokenize_request(request, tokenizer, device):
    return _tokenize_prompt_and_label(request["prompt"], request["target_new"], tokenizer, device)


def tokenize_unstructured_sample(sample, tokenizer, device):
    answer = sample["answer"]
    if not answer.startswith(" "):
        answer = " " + answer
    return _tokenize_prompt_and_label(sample["question"], answer, tokenizer, device)
