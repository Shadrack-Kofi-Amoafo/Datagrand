# Duplication findings — independent verification (2026-09-23)

**Scope:** all 22,200 generated records currently in `data/` (Layers 1–14).
**Question:** is the char n-gram report of ~9 badly-duplicated layers correct, and is the
"0 duplicates" claim in `data/all_14_layers_dedup_manifest.json` false?

**Answer:** yes on both counts. The stack/platform/noun-swap pattern is real, it is the
dominant failure mode of the corpus, and it is invisible to the hashed-word dedup that
produced the manifest. Everything below is reproducible with the two scripts added in this
commit; no threshold-guessing is required for the headline numbers.

---

## 1. How this was checked (and why the old method failed)

Three independent measurements, none of which depend on a tunable similarity threshold:

| Measure | Definition |
|---|---|
| **Frames** | distinct user messages with every fingerprint value, every backticked slot, and every file-tree/code payload masked — i.e. the sentence skeleton. Two samples that differ only by `React + Express + PostgreSQL` vs `Vue + FastAPI + PostgreSQL` count as **one** frame. |
| **Cells** | distinct `(entity, operation, constraint)` triples. The technology label is deliberately **excluded**: a stack is context, never a scenario. |
| **Redundant records** | records whose cell is already occupied by another record in the same layer. Padding by construction. |

Plus, where noted, char 5-gram cosine clustering at ≥ 0.90 (transitive closure), run on the
user message.

`audit_reports/duplication_forensics.py` produces the threshold-free numbers;
`audit_reports/pregen_dup_gate.py` enforces them as a pass/fail gate. Neither needs numpy
or sklearn.

**Why the manifest said "0 duplicates" for nine layers.** The dedup that produced
`data/all_14_layers_dedup_manifest.json` required `instruction_ngram_jaccard >= 0.9` **AND**
`embedding_cosine >= 0.98`, the latter being a 256-dimension signed hashed word embedding.
A sentence whose only change is one slot — `` `accounts` ``, `` `create_then_read` ``, one
stack name — stays at character level 97–99% identical, but the AND of two brittle
conditions almost never fires: the hashed word embedding collapses distinct slot values into
the same buckets (so cosine stays high but the 0.98 bar is not cleared on long instructions),
and word 5-gram Jaccard drops below 0.9 as soon as the sentence is long enough for the
swapped tokens to matter in a 5-gram window. The two-condition AND turned a real signal into
"no duplicates found". Independent of the arithmetic: the same generator wrote 3,000 Layer 9
records into **2** sentence frames, and no dedup tool should ever have reported that as clean.

---

## 2. Confirmed: the Layer 9 example is real, and it is systematic

The pair quoted in the report is representative, not an outlier. Layer 9:

- 3,000 records, **2** sentence frames (2,250 + 750).
- **306** scenario cells; worst cell repeated **10×**; label padding factor **9.8×**.
- char 5-gram clustering at ≥ 0.90 merges the whole layer into **2 clusters** (2,250 and 750).
- 2,694/3,000 records (90%) sit in a cell another record already occupies.

```
same cell (resource_noun=accounts, task_type=create_then_read, wiring_state=broken), 10 labels:
  Build a full round-trip for `React + Express + PostgreSQL` and `accounts` covering `create_then_read`...
  Build a full round-trip for `Vue + FastAPI + PostgreSQL` and `accounts` covering `create_then_read`...
  ... x8 more stacks
```

The same construction appears in every engineering layer:

| Layer | raw | cells | worst cell reuse | padding | frames | worst frame | char-ngram clusters ≥0.90 |
|---|---|---|---|---|---|---|---|
| 1 Tool Literacy | 1200 | 1200 | 1× | 1.0× | 522 | 50 (4%) | 234 clusters, largest 50 |
| 2 Navigation | 1300 | 1257 | 9× | 1.03× | **300** | 5 | 244 clusters, largest 78; **only 256 distinct symbols** for 1300 records |
| 3 Function Coding | 1795 | 1766 | 2× | 1.02× | 718 | 4 | 359 problem specs × 5 languages (declared); 828 distinct specs |
| 4 Debug Loop | 5 | 5 | 1× | 1.0× | 5 | 1 | 2,795 records missing |
| 5 Planning | 1600 | 1044 | 2× | 1.53× | **245** | 7 | 165 clusters; **0% contain a tool call** |
| 6 Frontend | 2600 | 524 | 5× | **4.96×** | **526** | 5 | 1013 clusters, largest 16 |
| 7 Backend | 2600 | 376 | 7× | **6.91×** | **38** | 351 (14%) | 91 clusters, largest 107; 96.9% in clusters ≥10 |
| 8 Database | 2200 | 225 | 10× | **9.78×** | **9** | 251 (11%) | **9 clusters cover 100%** |
| 9 Integration | 3000 | 306 | 10× | **9.8×** | **2** | 2250 (75%) | **2 clusters cover 100%** |
| 10 Env/Deps | 1200 | 120 | 10× | **10.0×** | **10** | 120 (10%) | 15 clusters cover 100% |
| 11 Testing | 2000 | 200 | 10× | **10.0×** | **12** | 200 (10%) | 10 clusters cover 100% |
| 12 Long-Horizon | 1200 | 125 | 10× | **9.6×** | **4** | 302 (25%) | **1 cluster covers 100%** |
| 13 Self-Correction | 1000 | 105 | 10× | **9.52×** | **1** | 1000 (100%) | **1 cluster covers 100%** |
| 14 Safety | 500 | 500 | 1× | 1.0× | **2** | 250 (50%) | 2 clusters cover 100% |
| **Total** | **22,200** | **7,753** | | | **2,394** | | **14,447 records (65.1%) share a cell** |

Exact figures: `audit_reports/duplication_forensics.json` (+ `.md` for the same table).

### Where the reported numbers land

The real numbers in the report are right in direction everywhere, and close in most layers.
Differences worth knowing before it is quoted as fact:

| Layer | reported real survives | this audit | note |
|---|---|---|---|
| 2 | 197 | 289 units / 300 frames | same conclusion (`far worse`); the exact denominator differs because I count `(symbol × task)` units while depth 1–5 restates them. 256 distinct symbols for 1,300 records is the cleanest way to say it. |
| 3 | 740 | 828 problem specs (5.5× language multiplier, declared) | agrees; the language axis is a defensible design choice, not padding — but the layer must be documented as 828 specs, not 1,795 samples. |
| 5 | 245 | 245 | exact match. The missing tool call is confirmed: **0/1,600** records contain any tool call, despite the "plan then act on step 1" requirement. |
| 6 | 580 | 524 cells / 526 frames | agrees (mine is slightly harsher). L6's padding is 5× (framework × styling) — a Cartesian pad, not reworded prose. |
| 7 | 1645 | 376 cells / 38 frames | disagrees, and worse than reported: 351 of 2,600 records share one frame, and 96.9% sit in char-ngram clusters of ≥10. |
| 8 | 223 | 225 cells / 9 frames | agrees on cells; note the frames are even worse — 9 sentence skeletons for 2,200 records. |
| 9 | 13 | 306 cells / 2 frames | disagrees, and worse: transitive char-ngram clustering merges everything into 2 clusters. Both readings support "essentially copy-pasted". |
| 10 | 119 | 120 cells / 10 frames | agrees. |
| 11 | 196 | 200 cells / 12 frames | agrees. |
| 12 | 11 | 35 units / 4 frames | agrees at the unit level; transitive clustering gives 1 cluster. |
| 13 | 19 | 105 cells / **1 frame** | agrees; the single frame for 1,000 records is the headline. |
| 14 | 330 | 500 cells / **2 frames** | disagrees in a narrower way: the *grid* is genuinely unique (500 distinct `(category, domain, group)` triples), so counting survivors overstates the damage; but 500 records are written from 2 templates, and 56% of the "domain" nouns are generic nouns burned in the engineering layers (`fees`, `folders`, `forecasts` with `credential_theft`), so the scenarios are semantically incoherent. It is not "the best of the bunch" — it is a different failure (linguistic collapse + incoherent pairing) that a survival count hides. |
| 1 | 458 | 522 frames | close. L1's primary defect is not duplication at all: 490/522 records are `asserted_not_shown` (verification never executed). Fix that in the same pass. |

### One metric that needs no thresholds at all

**14,447 of 22,200 records (65.1%) sit in a scenario cell that another record in the same
layer already occupies.** Across the entire corpus there are only **7,753 distinct scenario
cells** and **2,394 distinct instruction frames**. That is the whole dataset: 22,200 records
built from ~2.4k sentence skeletons, with the technology label doing most of the
differentiation.

---

## 3. Secondary finding: cross-layer noun recycling

The entity pools are drawn from one generic list and re-sampled across layers
(`audit_reports/pregen_dup_gate.py --all`, `noun_quarantine` check):

- L8 ∩ L9 = 25 shared nouns; L9 ∩ L14 = 38; L9 ∩ L11 = 20; L8 ∩ L14 = 25.
- Layer 14's "domain" pool shares 56% of its nouns with Layers 8/9/10/11.
- Layer 13 reuses 7 of 7 component nouns from other layers (`accounts`, `documents`, …).

So `accounts` is not merely re-used inside a layer: it is the subject of Layer 7 (handler),
8 (transaction), 9 (round-trip), 10 (env), 11 (test), 12 (long-horizon) and 14 (safety)
records. Even after fixing intra-layer padding, this makes layers correlated. The gate
therefore quarantines nouns already burned elsewhere (cap: 20% overlap, 5% for L14).

---

## 4. Verdict per layer (pre-generation gate, current corpus)

`python3 audit_reports/pregen_dup_gate.py --all` → **14/14 FAIL**. Full report:
`audit_reports/pregen_gate_report.json`.

| Layer | Failing checks |
|---|---|
| 1 | template_diversity (44% < 60%) — plus the separate grounding failure (93.9% ungrounded) |
| 2 | combo_uniqueness, entity_operation_uniqueness, template_diversity |
| 3 | combo_uniqueness (2×), entity_operation_uniqueness |
| 4 | pool_capacity (only 5 records exist) |
| 5 | tool_call_requirement, combo_uniqueness, entity_operation_uniqueness, template_diversity, pool_capacity |
| 6–13 | label_padding, combo_uniqueness, entity_operation_uniqueness, template_diversity, pool_capacity, noun_quarantine |
| 14 | template_diversity, pool_capacity, noun_quarantine |

Nothing here says the 7,753 cells are worthless. It says the corpus cannot be repaired by
dropping duplicates: for Layers 9/12/13 that leaves 306/35/105 cells, i.e. 10%/3%/10.5% of
target. The generator's constraint has to change before more budget is spent — that is what
`prompts/CORRECTIVE_GENERATION_PROMPT.md` does.

---

## 5. Reproduction

```bash
# threshold-free numbers (frames / cells / redundant records)
python3 audit_reports/duplication_forensics.py \
    --json audit_reports/duplication_forensics.json \
    --markdown audit_reports/duplication_forensics.md

# gate the existing corpus (all 14 layers)
python3 audit_reports/pregen_dup_gate.py --all --json audit_reports/pregen_gate_report.json

# gate one new batch before accepting it (this is the step to run before spending budget)
python3 audit_reports/pregen_dup_gate.py --layer 9 --input data/layer9_batch_new_500.jsonl --similarity
```
