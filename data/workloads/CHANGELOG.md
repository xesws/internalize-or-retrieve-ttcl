# Workload changelog

## v1.1 (2026-08-21, JQ ruling — G1 prerequisite 2)
- Temporal audit of free_scenario × supersede chains found **15 violations**
  (dev 3 / test 12): scenarios bundling an old (superseded) memory still
  expected the old value's keywords, but free_scenario probes evaluate at
  end-of-stream where the chain-final (new) value is correct.
- Fix: the 15 violating probes' `answer_keywords` rewritten to the chain-final
  value's keywords. Scenario text untouched (target-free ⇒ no temporal
  anchor). Machine-derived, no LLM calls.
- `answer_keywords` derivation changed to edge-trimmed full-phrase semantics
  (interior stopwords retained: " Coffee by Design" → "coffee by design");
  leading/trailing stopwords still dropped (" her aunt's cabin" →
  "aunt's cabin"). Non-scenario probes keep their v1 keywords except where
  the derivation change alters them — all re-linted 0 violations.
- Audit artifacts: `temporal_audit_v1.1.json` (full violation list).
- Gates re-verified on v1.1: schema 0 errors, lint 0 violations, turn
  mismatches 0 (both splits).

## v1 (2026-08-21)
- Initial freeze: dev 2 users / 104 memories / 363 probes; test 4 users /
  210 memories / 740 probes. See freeze_manifest_v1.json.
