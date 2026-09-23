# Corrective generation prompt — anti-“mad-libs” v2

**Use this before generating any further records, starting with Layers 4, 9, 12 and 13.**
It replaces the free-form "generate N samples for layer X" instruction with a
grid-first procedure that a machine can check.

Evidence for why this is needed: `audit_reports/DUPLICATION_FINDINGS_2026-09-23.md`.
Enforcement: `audit_reports/pregen_dup_gate.py` (run it on every batch before the next one is
commissioned). Current corpus fails the gate in all 14 layers.

---

## Part 1 — Pre-flight worksheet (must be produced and approved BEFORE any sample)

The generator must not write samples first and dedup later. It must declare the grid, prove
it has enough headroom, and only then realise the samples. Output this as
`data/grids/layer{N}_grid.json` with these keys:

```json
{
  "layer": 9,
  "target": 3000,
  "entity_axis":   {"name": "resource_noun", "pool": ["...", "..."], "size": 0},
  "operation_axis":{"name": "task_type",     "pool": ["...", "..."], "size": 0},
  "constraint_axis":{"name": "wiring_state", "pool": ["...", "..."], "size": 0},
  "label_axis":    {"name": "stack", "pool": ["...", "..."], "size": 0,
                    "rule": "labels may appear in at most 1 sample per scenario cell"},
  "capacity": 0,
  "planned_batches": [{"batch": 1, "cells": 0, "distinct_frames_required": 250}],
  "frame_plan": ["frame template 1", "frame template 2", "..."],
  "declared_variant_axes": []
}
```

**Admission rule (hard).** `capacity = |entities| × |operations| × |constraints|` must be at
least `1.5 × target` with `max_combo_reuse = 1`. If it is not, expand the pools first — do not
generate. A batch whose samples exceed capacity is guaranteed to be padding, and the gate
will reject it.

**Frame plan (hard).** Declare at least `0.6 × target` distinct sentence frames up front, each
a different way of describing the work (different invariant, different failure mode, different
definition of done, different evidence required). Every scenario must be *written*, not
filled in.

---

## Part 2 — Hard rules handed to the generator (paste this block verbatim)

```text
You are generating training trajectories for the layer named below. Read all rules before
writing anything. Any sample that violates a rule is discarded and does not count toward the
target.

RULE 1 — Vary the substance, not the label.
No two samples in a layer may share both the same entity noun and the same operation,
regardless of stack, framework, runtime, platform or engine. `accounts` + `create_then_read`
presented across ten stacks is ONE sample with a find-and-replace, not ten.

RULE 2 — No repeated scenario cell.
No two samples may share the same (entity, operation, constraint) cell, where the constraint
axis is the layer's real scenario axis (wiring_state, horizon_steps, target_depth,
spec_style, calibration_group, ...). A technology label is never the constraint axis and is
never sufficient to distinguish two samples.

RULE 3 — Labels are context, never content.
A framework/runtime/stack may appear in at most one sample per scenario cell. A variant
dimension only counts as legitimate if it is declared in `declared_variant_axes` AND changes
what the model must actually do (e.g. the same problem implemented in a different language,
with different idioms and a different toolchain).

RULE 4 — Write new sentences.
At least 60% of samples in a batch must use a distinct sentence frame, and no single frame may
cover more than 5% of the batch. Changing a noun inside an otherwise identical sentence does
not create a new frame.

RULE 5 — Be concrete, not generic.
Entity nouns must be specific to this layer's subject matter and must not be reused from
another layer's pool. Forbidden: generic nouns already burned elsewhere (`accounts`,
`bookings`, `documents`, `alerts`, ...) unless the layer declares a topic-scoped list and the
noun appears in at most 5% of the batch.

RULE 6 — Realistic scenarios, coherent pairings.
Every (entity, operation) pair must be plausible in the real world. "credential_theft
involving fees" is not a scenario; a category and its subject must be drawn from the same
topic scope.

RULE 7 — Evidence, not assertion.
Every trajectory must execute its verification in the tool trace, and the final claim must
reference the observed output. Asserting success without running the check is a failed sample.
Layers that require a first-step action must contain an actual tool call in the assistant turn
(see Layer 5 below).

RULE 8 — Report the honest count.
When you report completion, state: records generated, distinct scenario cells, distinct
sentence frames, largest frame, worst cell reuse, and the label padding factor
(records / cells). Missing any of these is an incomplete report.

BEFORE WRITING SAMPLES: emit the grid worksheet for this layer and state the capacity
calculation. If capacity < 1.5 x target, stop and report that the entity pool must be expanded
first.
```

---

## Part 3 — Per-layer directives (with the real headroom numbers)

Pools below are the pools that exist today; "needed" is what admission requires. Anything
marked **EXPAND FIRST** will fail the gate no matter how well it is written.

### Layer 9 — Integration round-trip · target 3,000 · **EXPAND FIRST**

- Cells today: 43 entities × 8 operations × 2 wiring states = 306. Capacity needed: ≥ 4,500.
- **Entity pool must go from 43 to ≥150**, topic-scoped and layer-specific (e.g. payment
  settlement, inventory reservations, subscription entitlements, clinical appointments —
  each with real fields, not a bare noun).
- Add a third constraint axis that changes the work: e.g. `concurrency_model`
  (single writer, optimistic version, pessimistic lock) or `boundary` (HTTP handler,
  queue consumer, scheduled job). With 150 entities: 150 × 8 operations × 2 wiring states
  × 3 boundaries = 7,200 cells ≥ the 4,500 required.
- Frame requirement: ≥1,800 distinct frames for the layer. Every scenario needs its own
  statement of the invariant being proven (double-entry balance, no lost update, idempotent
  retry, tenant isolation, ...).
- The embedded `wiring_state` dimension stays, but a broken-wiring sample must also differ in
  entity, operation and invariant from every other broken-wiring sample.

### Layer 12 — Long-horizon trajectories · target 1,200 · **EXPAND FIRST**

- Cells today: 9 domains × 8 trajectory types = 35 (entity, operation) units, repeated up
  to **40×** each (10 systems × 4 horizon values), delivered through **4** frames. This is a
  single template with two slots.
- **Rebuild the scenario axis**: `{domain} × {trajectory type} × {interruption point} ×
  {checkpoint strategy}`, with ≥30 layer-specific domains × 8 types × 4 interruption points
  (mid-write, mid-commit, between steps, during rollback) × 3 checkpoint strategies.
- Frame requirement: ≥600 distinct frames. Each trajectory needs a distinct invariant,
  distinct resumability argument, and distinct evidence of idempotency.
- Schema fix in the same pass: records must carry the required `state_checkpoints` key
  (today 1,200/1,200 use `checkpointed` + `horizon_steps` instead).

### Layer 13 — Self-correction under failure · target 1,000 · **EXPAND FIRST**

- Cells today: 7 components × 10 failures × 8 strategies = 105, delivered in **1** frame.
  All 1,000 records are one char-ngram cluster.
- **Component pool must go from 7 to ≥150** and must be *failure-relevant* (connection pool,
  migration runner, token cache, retry queue, ...), not a generic noun.
- Add an evidence axis: what observation distinguishes this failure from its look-alike
  (timeout vs slow success, stale connection vs rolled-back transaction, duplicate delivery vs
  at-least-once retry).
- Frame requirement: ≥500 distinct frames; every recovery must have its own diagnosis
  narrative and bounded retry budget.
- Runtime stays a label: at most one sample per (component, failure, strategy, evidence) cell.

### Layer 4 — Localized debug loop · target 2,800 · **EXPAND FIRST (2,795 records missing)**

- Only 5 records have ever been generated. Start from the grid, not from these 5.
- Grid: `{bug_category} × {language} × {symptom_presentation} × {codebase context}`, where
  context is a concrete module family (date/time handling, pagination, currency rounding,
  retry backoff, auth token refresh, cache invalidation, ...).
- Requirement: ≥1,000 distinct bug scenarios, each with a real failing test, a real
  hypothesis→edit→rerun→revise loop, and the disproved hypothesis left visible in the trace.

### Layer 8 — Database · target 2,200

- Cells today: 30 objects × 9 task types = 225, padded 10× by engine. Worst cell reuse 10;
  **9** frames for 2,200 records.
- Objects must expand to ≥250 and be schema-shaped (`orders`, `order_items`,
  `payment_attempts`, `inventory_ledger`, ...) with task-specific constraints (isolation
  level, uniqueness, foreign-key behaviour, migration safety).
- Engine stays a label. Frame requirement: ≥900.

### Layer 10 — Runtime environment & config · target 1,200

- Cells today: 12 nouns × 10 task types = 120, padded 10× by runtime, **10** frames.
- Expand to ≥150 real environment artefacts (lockfile policy, secret manager rotation, CI
  matrix, container base image, cache key, env-var precedence, ...) and make each task differ
  in the failure it prevents.
- Frame requirement: ≥600.

### Layer 11 — Testing · target 2,000

- Cells today: 20 subjects × 10 task types = 200, padded 10× by test runner, **12** frames.
- Expand to ≥250 subjects; add an assertion-design axis (boundary, ordering,
  idempotency, error contract, isolation, cleanup) so different samples demand different
  evidence.
- Frame requirement: ≥1,000.

### Layer 7 — Backend handlers · target 2,600

- Cells today: 58 resources × 7 task types = 376, padded 7× by framework, **38** frames
  (351 records share one frame).
- Expand the resource bank to ≥400 layer-specific resources and add an API-contract axis
  (pagination style, error taxonomy, idempotency key, auth model).
- Frame requirement: ≥1,300. Do not phrase seven different resources with one sentence.

### Layer 6 — Frontend · target 2,600

- Cells today: 521 elements × 10 task types = 524, padded 5× by framework × styling.
- Expand distinct elements/interaction tasks to ≥1,300 (keyboard navigation, focus trap,
  optimistic update, suspense fallback, form interruption, reduced-motion, ...).
- Frame requirement: ≥1,300. Framework is a label.

### Layer 5 — Planning · target 1,600

- 245 frames for 1,600 records, and **0/1,600 samples contain a tool call** despite the
  "plan then act on step 1" requirement.
- Regenerate so that every trajectory: (a) asks the blocking question, (b) produces an
  ordered plan, (c) **issues a real tool call to execute step 1** (create the skeleton,
  scaffold the first migration, open the first file), and (d) reports the observed result.
- Expand domains to ≥120 and require ≥900 distinct frames (the plan narrative, not the
  domain name, must differ).

### Layer 2 — Navigation · target 1,300

- 1,300 records, only **256** distinct symbols and 264 distinct entry paths; the same symbol is
  re-described at depths 1–5 inside a byte-identical sentence.
- Requirement: ≥500 distinct (symbol × task_type) units, each with its own question wording,
  and depths must apply to *different* symbols rather than restating one.
- Frames: ≥780.

### Layer 1 — Tool literacy · target 1,200

- The grid is fine (1,200 unique cells); the two real defects are (a) 522 frames for 1,200
  records — 50 records share one frame, and (b) **490/522 records never execute the
  verification command** (`asserted_not_shown`).
- Regenerate with: distinct phrasing per task, a tool call in every trajectory, and a final
  claim that quotes the observed output.

### Layer 3 — Function coding · target 1,800

- Structurally the healthiest layer: 828 distinct problem specs, each implemented across
  languages. Keep it, but stop reporting it as 1,800 unique samples.
- Requirement: declare `language` in `declared_variant_axes`; report "828 problem specs ×
  5 language implementations"; ensure each language version is idiomatic (not a transliteration)
  and that no problem spec appears twice within one language.

### Layer 14 — Safety calibration · target 500

- The grid is unique (500 cells, 50/50 refusal/safe split), but there are **2** frames for 500
  records, and 56% of the "domain" nouns are generic nouns burned in the engineering layers
  (`fees`, `folders`, `forecasts`), producing incoherent pairs such as
  `credential_theft involving fees`.
- Rebuild: ≥250 category-scoped subjects (each category draws from its own pool), ≥50 distinct
  request frames, and a distinct boundary statement per category. Keep the 50/50 calibration.

---

## Part 4 — Generation loop (no batch without a gate)

```bash
# 1. write the grid worksheet and check capacity
python3 - <<'PY'
cap = 150 * 8 * 3          # layer 9 example: entities x operations x constraints
print("capacity", cap, "| required", 1.5 * 3000)
PY

# 2. generate ONE batch (<= 500 records, <= 50% of remaining capacity)

# 3. gate it against everything already accepted before commissioning the next batch
python3 audit_reports/pregen_dup_gate.py \
    --layer 9 --input data/layer9_batch_new_001.jsonl --similarity \
    --json audit_reports/layer9_batch_new_001.gate.json
# exit code 0 = accept; 1 = reject and regenerate the violating samples only
```

Gate thresholds the prompt is aligned to (`audit_reports/pregen_gate_config.json`): distinct
cells ≥ 1 per sample, no cell reuse, no shared entity+operation, label padding ≤ 2×
(5.5× for Layer 3's declared language axis), ≥50% distinct frames (≥60% for Layers 1–3),
no frame >5% of the batch, entity pool ≥ the per-layer minimum, noun quarantine ≤20%
(≤5% for Layer 14).

## Part 5 — Budget order (do not skip step 1)

1. **Rebuild the entity pools** for Layers 8, 9, 10, 11, 12, 13 (and 6, 7 to their new sizes).
   Until this exists, every generated sample is a re-skin by construction.
2. **Regenerate** Layers 9, 12, 13, 4 (highest severity: 65% of the corpus's padding lives
   here, and Layer 4 is 0.2% complete). Gate each 500-record batch.
3. **Regenerate** Layers 5 (tool calls + frames) and 1 (grounding).
4. **Expand** Layers 7, 8, 10, 11, 6 to their pool sizes, then regenerate.
5. **Keep** Layer 3 with its declared language axis; **rebuild** Layer 14's scenario text;
   **trim** nothing else — dropping duplicates leaves 306/35/105 cells for Layers 9/12/13.
