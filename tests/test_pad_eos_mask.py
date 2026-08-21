"""CPU unit tests for the §4.1 pad/eos mask patch (handbook red line).

The fake tokenizer mirrors the Llama hazard exactly: pad_token_id == eos
(aliased), right padding. Assertions encode the three invariants:
  (1) the target-final eos stays SUPERVISED even though eos == pad id;
  (2) exactly the prompt prefix is masked (attention-based count, no
      off-by-one when the prompt encoding ends in eos);
  (3) only true padding (attention_mask == 0) is masked, never real tokens;
plus the HOREN.edit key_id formula landing on the last prompt token.
"""
import torch

from horen_backend.models.horen.utils import _tokenize_prompt_and_label

EOS = 9  # aliased: pad_token_id == eos_token_id, like the Llama tokenizer


class FakeTok:
    """Str -> fixed id lists; right-pads with EOS like HF Llama default."""

    pad_token_id = EOS

    def __init__(self, table: dict):
        self.table = table

    def __call__(self, texts, return_tensors="pt", padding=True, truncation=True, **kw):
        id_lists = [self.table[t] for t in texts]
        maxlen = max(len(x) for x in id_lists)
        input_ids = torch.full((len(id_lists), maxlen), EOS, dtype=torch.long)
        attention_mask = torch.zeros(len(id_lists), maxlen, dtype=torch.long)
        for i, ids in enumerate(id_lists):
            input_ids[i, : len(ids)] = torch.tensor(ids, dtype=torch.long)
            attention_mask[i, : len(ids)] = 1
        return {"input_ids": input_ids, "attention_mask": attention_mask}


# prompt encoding ends in a REAL eos; target encoding also ends in eos
TOK = FakeTok({
    "p": [1, 2, 3, EOS],          # prompt alone: 4 tokens incl. trailing eos
    "p t": [1, 2, 3, EOS, 5, 6, EOS],  # full = prompt + target (+final eos)
    "p2": [1, 2, 3, EOS, 4],      # longer prompt (batch-padding case)
    "p2 t": [1, 2, 3, EOS, 4, 5, 6, EOS],
})


def test_target_final_eos_is_supervised_despite_pad_alias():
    tokens = _tokenize_prompt_and_label(["p"], ["t"], TOK, "cpu")
    labels = tokens["labels"][0]
    # the answer's terminating eos is a real supervised training target
    assert labels[-1].item() == EOS
    assert labels[-1].item() != -100
    # legacy behaviour this patch removes: labels[input_ids == pad] == -100
    # erased that stop signal — document the contrast explicitly
    legacy = labels.clone()
    legacy[tokens["input_ids"][0] == TOK.pad_token_id] = -100
    assert legacy[-1].item() == -100


def test_prompt_prefix_exactly_masked_no_off_by_one():
    tokens = _tokenize_prompt_and_label(["p"], ["t"], TOK, "cpu")
    labels = tokens["labels"][0]
    # attention-based count: prompt occupies 4 positions (incl. its eos)
    assert (labels == -100).sum().item() == 4
    assert labels[:4].tolist() == [-100] * 4
    assert labels[4:].tolist() == [5, 6, EOS]
    # legacy count `!= pad_id` over the PROMPT-ONLY encoding yielded 3
    # (it skipped the prompt's real trailing eos) — the off-by-one just fixed
    prompt_only = TOK(["p"], return_tensors="pt")["input_ids"][0]
    legacy_count = int((prompt_only != TOK.pad_token_id).sum().item())
    assert legacy_count == 3


def test_horen_key_id_lands_on_last_prompt_token():
    tokens = _tokenize_prompt_and_label(["p"], ["t"], TOK, "cpu")
    # exact formula from HOREN.edit (horen_backend/models/horen/editor.py)
    key_id = int((tokens["labels"] == -100).sum(dim=1).min().item() - 1)
    assert key_id == 3  # index of the LAST prompt token, not the first target


def test_batch_padding_masked_via_attention_only():
    tokens = _tokenize_prompt_and_label(["p", "p2"], ["t", "t"], TOK, "cpu")
    am, labels = tokens["attention_mask"], tokens["labels"]
    assert am.shape == labels.shape == (2, 8)
    assert am[0].tolist() == [1] * 7 + [0]  # row 0 padded by one
    # every true pad position masked
    assert (labels[am == 0] == -100).all()
    # every real token in the supervised span kept (incl. each row's final eos)
    for row, n_prompt in ((0, 4), (1, 5)):
        span = labels[row][am[row] == 1]
        assert (span[:n_prompt] == -100).all()
        assert (span[n_prompt:] != -100).all()
        assert span[-1].item() == EOS


def test_patch_marker_present():
    # guard against accidental revert of the §4.1 red-line patch
    import inspect

    src = inspect.getsource(_tokenize_prompt_and_label)
    assert "attention_mask" in src
    assert "!= tokenizer.pad_token_id" not in src  # legacy count must be gone
    assert "PATCH (ttcl" in src
