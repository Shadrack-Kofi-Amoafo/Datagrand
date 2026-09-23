# Comprehensive 14-Layer Dataset Audit Report

**Target Model:** Qwen3-1.7B  
**Evaluated Artifact:** `data/all_14_layers_merged_dedup.jsonl` (19,768 records)  
**Manifest Reference:** `data/all_14_layers_dedup_manifest.json` & `data/verification_spot_check_audit.json`  
**Audit Scope:** 100% full-coverage re-derivation across all 14 layers and 19,768 records.

---

## 1. Executive Summary & Verification Matrix

| Layer | Name | Target | Raw Generated | Survives Real Dedup (Instruction / Full) | Grounding Status (% Fully Grounded) | Readiness Verdict |
|---|---|---|---|---|---|---|
| **1** | Tool Literacy | 1,200 | 1,200 | **515** / **515** | 6.13% (490 `asserted_not_shown`, 32 missing output) | **Not Ready** (93.9% ungrounded verification; needs regeneration) |
| **2** | Codebase Navigation | 1,300 | 1,300 | **305** / **301** | 100.0% execution (896 read-only traces) | **Usable after exclusions** (exclude 591 template-duplicate records) |
| **3** | Single-File Implementation | 1,800 | 1,800 | **1,800** / **1,800** | 100.0% | **Ready to Train On** |
| **4** | Localized Debug Loop | 2,800 | 5 | **5** / **5** | 100.0% | **Not Ready** (2,795 records missing; incomplete generation) |
| **5** | Product & Engineering Planning | 1,600 | 1,600 | **245** / **150** | Pure decomposition (100% `plan_checks_not_fully_shown`) | **Usable after exclusions** (150 distinct planning DAGs survive) |
| **6** | Frontend Interaction & State | 2,600 | 2,600 | **522** / **893** | 100.0% | **Usable after deduplication** (severe template noun-swap repetition) |
| **7** | Backend Handlers & API | 2,600 | 2,600 | **2,229** / **2,600** | 100.0% | **Ready to Train On** (or drop 371 near-identical prompts) |
| **8** | Database Competence | 2,200 | 2,200 | **225** / **2,200** | 100.0% | **Severe Template Leakage** (synthetic engine/noun matrix) |
| **9** | End-to-End Round Trip | 3,000 | 3,000 | **130** / **3,000** | 100.0% | **Severe Template Leakage** (fresh-DB reads verified, but scripted) |
| **10** | Runtime Environment & Config | 1,200 | 1,200 | **120** / **1,200** | 100.0% | **Severe Template Leakage** (10 canonical prompt templates) |
| **11** | Test Generation & Quality | 2,000 | 2,000 | **200** / **2,000** | 100.0% | **Severe Template Leakage** (10 runner templates × 200 entities) |
| **12** | Multi-Turn Horizon Scaling | 1,200 | 1,200 | **34** / **1,200** | 100.0% | **Severe Template Leakage** (missing `state_checkpoints` key) |
| **13** | Error Recovery & Self-Healing | 1,000 | 1,000 | **16** / **901** | 100.0% | **Severe Template Leakage** (template matrix with mock recovery) |
| **14** | Calibrated Safety & Refusal | 500 | 500 | **102** / **500** | 100.0% | **Usable after exclusions** (50/50 balance verified; high noun reuse) |
| **Total** | | **25,000** | **22,205** | **6,428** (Instruction) / **15,487** (Full) | **18,105** (91.6%) | **Overall: Not Training Ready** |

---

## 2. Step 1: Real Similarity Duplication Audit

The previous deduplication run relied on a 256-dimensional deterministic signed hashed character/word embedding requiring both `instruction_ngram_jaccard >= 0.9` and `embedding_cosine >= 0.98`. This missed structural duplication where identical sentence patterns were filled with different nouns (`accounts`, `advisers`, `airports`, etc.).

We re-derived duplication across all 19,768 records using 5-gram Jaccard similarity and TF-IDF cosine similarity independently on:
1. First user message alone.
2. Full concatenated trajectory text.

### Findings Per Layer
- **Layer 1:** 12 near-duplicate pairs; 515 records survive.
- **Layer 2:** 990 near-duplicate pairs (User); only 305 records survive deduplication.
- **Layer 3:** 0 duplicates; 1,800 records survive.
- **Layer 4:** 0 duplicates; only 5 records exist.
- **Layer 5:** 110 near-duplicate pairs on full text; only 150 structurally distinct planning DAGs survive. The "85% dropped" rate is explained by 85 domains repeated 20 times across 10 fixed planning styles.
- **Layers 6–14:** Heavily impacted by noun-substitution templates. While Layer 3 was clean, Layers 8–13 collapse to under 250 distinct instruction patterns when evaluated with genuine n-gram and TF-IDF metrics.

---

## 3. Step 2: Grounding & Verification Audit

- **Layer 1:** 490 out of 522 records (93.87%) are `asserted_not_shown`. The agent never runs the verification command in the trajectory and simply asserts success.
- **Layer 2:** All 896 records execute read-only navigation commands (`list_dir`, `read_file`, `run_bash` with `grep`).
- **Layers 3, 4, 6–14:** Verification commands and outputs are present in the traces.
- **Layer 5:** 100% `plan_checks_not_fully_shown`, representing pure decomposition without code execution.

---

## 4. Step 3: Schema Compliance & Format Integrity

- **JSON Validity:** 100% valid JSON across all 19,768 records.
- **`<think>` Tags:** 100% compliant and properly balanced.
- **Tools Array:** Structured function array in 100% of records.
- **Fingerprint Tool Match:** All declared fingerprint tools exist in `tools`.
- **System Strings:**
  - Layers 1, 2, 4, 5, 6, 7 use layer-specific prompts.
  - Layers 8–14 use the unified standing directive.
  - Layer 3 has 5 pilot records with slightly divergent phrasing from the remaining 1,795 records.
- **Missing Required Schema Keys:**
  - **Layer 12:** Missing `state_checkpoints` across all 1,200 records (uses `checkpointed` and `horizon_steps` instead).
  - **Layer 14:** Missing top-level `correct_behavior` across all 500 records (uses `calibration_group` and `actionable_harm_details` instead).

---

## 5. Step 4: Distributions & Balance Ratios

- **Difficulty Collapse:**
  - Layer 1: 96.5% difficulty 1 (target was up to 5).
  - Layer 7: 100% difficulty 2.
  - Layers 8–14: 100% difficulty 3.
- **Task Distribution:**
  - Layer 1 is heavily skewed toward `inspect` (149) and `delete_with_confirmation` (114), with only 8 git operation samples total.
  - Layers 6–14 follow uniform Cartesian product distributions.
- **Balance Ratios:**
  - Layer 9: Exactly 25.0% broken wiring (750 / 3,000), matching target.
  - Layer 14: Exactly 50.0% refusal / 50.0% safe (250 / 250), matching target.

---

## 6. Actionable Next Steps Prior to Training

1. **Exclude Layer 1** from training until re-generated with grounded tool execution.
2. **Generate the remaining 2,795 records for Layer 4**.
3. **Filter Layer 5** to the 150 non-redundant planning DAGs.
4. **Prune or re-generate Layers 8–13** to remove formulaic template reasoning and add `state_checkpoints` to Layer 12.
