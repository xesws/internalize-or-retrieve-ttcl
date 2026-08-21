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

    tokens = tokenizer(full_prompt, return_tensors="pt", padding=True, truncation=True)
    labels = tokens["input_ids"].clone()
    for i in range(len(prompt)):
        labels[i][: num_prompt_toks[i]] = mask_token
    # PATCH (ttcl §4.1, 2026-08-21): mask ONLY true padding (attention_mask == 0).
    # Upstream masked `input_ids == pad_token_id`, which — under the pad=eos
    # alias — also erased the target-final eos from the training labels and left
    # the editor training with no stop signal (runaway generation at decode).
    # A real eos inside the supervised target span must stay supervised.
    labels[tokens["attention_mask"] == 0] = mask_token
    tokens["labels"] = labels

    return {k: v.to(device) for k, v in tokens.items()}


def tokenize_request(request, tokenizer, device):
    return _tokenize_prompt_and_label(request["prompt"], request["target_new"], tokenizer, device)


def tokenize_unstructured_sample(sample, tokenizer, device):
    answer = sample["answer"]
    if not answer.startswith(" "):
        answer = " " + answer
    return _tokenize_prompt_and_label(sample["question"], answer, tokenizer, device)
