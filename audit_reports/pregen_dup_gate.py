#!/usr/bin/env python3
"""Pre-generation duplication gate for the 14-layer dataset.

Run this on EVERY new batch BEFORE the batch is accepted (and before the next
batch is commissioned). It fails a batch that is a stack/platform/noun swap of
records that already exist, or that is internally templated.

Why it exists
-------------
The manifest (data/all_14_layers_dedup_manifest.json) reported "raw == dedup"
for layers 3 and 6-14. That was produced with a signed-hashing word embedding
plus a 5-gram Jaccard requirement AND-ed together (|ngram_jaccard >= 0.9| and
|cosine >= 0.98|). A generator that keeps the sentence and swaps one label
("React + Express + PostgreSQL" -> "Vue + FastAPI + PostgreSQL") produces
documents that are 97-99% identical as character n-grams, yet score far below
0.98 under that hashed-word cosine and below 0.9 Jaccard once the sentence is
long enough. The result: 2,994 of 3,000 Layer 9 records sit in a single
near-duplicate cluster, and the manifest called the layer clean.

This gate works on the three axes that actually distinguish samples:
  entity    - the noun the sample is about        (accounts, invoices, bookings)
  operation - what is done to it                  (create_then_read, ownership_authorization)
  mode      - the constraint/failure/context axis (wiring_state, horizon_steps, engine)
plus a template signature: the user message with all fingerprint values masked.
Two samples with the same entity+operation+mode are the same sample even if one
says React and the other says Vue. Two samples with different slots but the same
template signature are the same sentence with different words.

Usage
-----
  python3 audit_reports/pregen_dup_gate.py --layer 9 --input data/layer9_batch_new_500.jsonl
  python3 audit_reports/pregen_dup_gate.py --layer 12 --input 'data/layer12_batch4_*.jsonl' --json out.json
  python3 audit_reports/pregen_dup_gate.py --layer 9 --input data/layer9_all_3000.jsonl --similarity
  python3 audit_reports/pregen_dup_gate.py --all           # audit every existing corpus file

Exit code 0 = PASS (batch is safe to accept), 1 = FAIL, 2 = usage/config error.

No third-party dependencies (no numpy/sklearn on purpose: the previous audit's
weakness came from trusting a vectorizer, not from words).
"""

import argparse
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(HERE, "pregen_gate_config.json")


# ---------------------------------------------------------------- loading ---

def load_config(path=CONFIG_PATH):
    with open(path) as fh:
        return json.load(fh)


def load_jsonl(paths):
    records = []
    files = []
    for pattern in paths:
        matched = sorted(glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern])
        for path_ in matched:
            if not os.path.isfile(path_):
                continue
            if os.path.getsize(path_) == 0:
                files.append(path_)
                continue
            with open(path_) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            files.append(path_)
    return records, files


def user_message(record):
    for msg in record.get("messages", []):
        if msg.get("role") == "user":
            return msg.get("content") or ""
    return ""


def assistant_text(record):
    return "\n".join(m.get("content") or "" for m in record.get("messages", [])
                     if m.get("role") == "assistant")


# ------------------------------------------------------------- signatures ---

BACKTICK_RE = re.compile(r"`([^`]+)`")


def extract_symbol(record):
    """For Layer 2 style records: the identifier being navigated to."""
    fp = record.get("fingerprint", {})
    for key in ("symbol", "target_symbol", "function_name"):
        if fp.get(key):
            return str(fp[key])
    found = BACKTICK_RE.findall(user_message(record))
    return found[0] if found else ""


def slot(record, field, cfg=None):
    fp = record.get("fingerprint", {})
    if field == "symbol":
        value = extract_symbol(record)
    else:
        value = fp.get(field)
        if value is None:
            value = ""
        value = str(value)
    normalizer = ((cfg or {}).get("normalizers") or {}).get(field) or {}
    regex = normalizer.get("strip_prefix_regex")
    if regex:
        value = re.sub(regex, "", value)
    return " ".join(value.lower().split())


def constraint_fields(cfg):
    """Real scenario axes only. A technology label is never a scenario axis: putting
    `stack` in the cell key is what let the old audit call 3000 stack-swaps unique."""
    if cfg.get("constraint_fields") is not None:
        return cfg["constraint_fields"]
    labels = set(cfg.get("label_fields", []))
    return [f for f in cfg.get("mode_fields", []) if f not in labels]


def combo_key(record, cfg):
    return tuple(
        [("E", f, slot(record, f, cfg)) for f in cfg["entity_fields"]]
        + [("O", f, slot(record, f, cfg)) for f in cfg["operation_fields"]]
        + [("C", f, slot(record, f, cfg)) for f in constraint_fields(cfg)]
    )


def entity_operation_key(record, cfg):
    return tuple(
        [("E", f, slot(record, f, cfg)) for f in cfg["entity_fields"]]
        + [("O", f, slot(record, f, cfg)) for f in cfg["operation_fields"]]
    )


def label_key(record, cfg):
    return tuple((f, slot(record, f, cfg)) for f in cfg.get("label_fields", []))


def template_signature(record, cfg, extra_values=()):
    """User message with every fingerprint value (and label token) masked.

    'Build a full round-trip for `React + Express + PostgreSQL` and `accounts`
     covering `create_then_read`...'
    'Build a full round-trip for `Vue + FastAPI + PostgreSQL` and `accounts`
     covering `create_then_read`...'
    both become 'build a full round-trip for <x> and <x> covering <x>...' i.e.
    one frame, which is the point.
    """
    text = user_message(record).lower()
    values = set(extra_values)
    for value in record.get("fingerprint", {}).values():
        if isinstance(value, str) and len(value) > 2:
            values.add(value.lower())
    # Drop file-tree / box-drawing lines and fenced code: those are the payload the
    # sample is about, not the sentence frame the generator reused.
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^[\u2500-\u257f|`]", stripped):
            continue
        if stripped.startswith("file tree") or stripped.startswith("snippet"):
            continue
        kept.append(stripped)
    text = " ".join(kept)
    # Keep only the instruction: everything from the first payload marker onwards is the
    # artefact being operated on (file tree, snippets), not the sentence frame.
    marker = re.search(r"(file tree|snippet|summarized below|repo tree|context:|```)", text)
    if marker:
        text = text[:marker.start()]
    for value in sorted(values, key=len, reverse=True):
        if value.strip():
            text = text.replace(value, " <x> ")
    # Backticked spans are always slot values in this corpus (symbols, paths, stacks,
    # nouns); masking them is what makes "where is `a` defined" and
    # "where is `b` defined" the same frame instead of two.
    text = re.sub(r"`[^`]*`", " <slot> ", text)
    text = re.sub(r"[^a-z0-9<>]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------- similarity ---

def norm_text(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s`+_./-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ngram_vector(text, n=5):
    text = norm_text(text)
    if len(text) < n:
        grams = Counter({text: 1}) if text else Counter()
    else:
        grams = Counter(text[i:i + n] for i in range(len(text) - n + 1))
    vec = {g: 1 + math.log(f) for g, f in grams.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {g: v / norm for g, v in vec.items()}


def similarity_conflicts(batch_texts, ref_texts, threshold, ngram, pair_cap=4_000_000):
    """Union-find over cosine >= threshold. Returns (clusters for batch, conflicts)."""
    vecs = [ngram_vector(t, ngram) for t in batch_texts]
    ref_vecs = [ngram_vector(t, ngram) for t in ref_texts]
    index = defaultdict(list)
    for i, v in enumerate(vecs):
        for g in v:
            index[g].append(i)
    parent = list(range(len(vecs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    pairs = 0
    capped = False
    for i, v in enumerate(vecs):
        acc = defaultdict(float)
        for g, w in v.items():
            for j in index[g]:
                if j > i:
                    acc[j] += w * v[g]
        for j, score in acc.items():
            pairs += 1
            if pairs > pair_cap:
                capped = True
                break
            if score >= threshold:
                union(i, j)
        if capped:
            break

    ref_index = defaultdict(list)
    for j, rv in enumerate(ref_vecs):
        for g in rv:
            ref_index[g].append(j)
    ref_conflicts = 0
    ref_pairs = 0
    for v in vecs:
        acc = defaultdict(float)
        for g, w in v.items():
            for j in ref_index[g]:
                acc[j] += w * ref_vecs[j][g]
        ref_pairs += len(acc)
        if acc and max(acc.values()) >= threshold:
            ref_conflicts += 1

    clusters = Counter(find(i) for i in range(len(vecs)))
    sizes = sorted(clusters.values(), reverse=True)
    return {
        "batch_clusters": len(clusters),
        "largest_cluster": sizes[0] if sizes else 0,
        "samples_in_cluster_ge_10": sum(s for s in sizes if s >= 10),
        "batch_pairs_compared": pairs,
        "pair_cap_hit": capped,
        "records_matching_reference": ref_conflicts,
        "reference_pairs_compared": ref_pairs,
    }


# ------------------------------------------------------------------ checks ---

def check_schema(records, cfg):
    missing_messages = 0
    missing_fingerprint = 0
    for record in records:
        if not record.get("messages"):
            missing_messages += 1
        if not isinstance(record.get("fingerprint"), dict) or not record["fingerprint"]:
            missing_fingerprint += 1
    fails = []
    if missing_messages:
        fails.append(f"{missing_messages} records without messages")
    if missing_fingerprint:
        fails.append(f"{missing_fingerprint} records without fingerprint")
    return {"pass": not fails, "detail": "; ".join(fails) or "ok",
            "metrics": {"records": len(records)}}


def check_tool_calls(records, cfg):
    if not cfg.get("requires_tool_call"):
        return {"pass": True, "detail": "not required for this layer", "metrics": {}}
    missing = [i for i, r in enumerate(records)
               if "<tool_call>" not in assistant_text(r)]
    return {
        "pass": not missing,
        "detail": f"0 records contain a tool call" if len(missing) == len(records)
                  else f"{len(missing)} records contain no tool call",
        "metrics": {"records_without_tool_call": len(missing), "records": len(records),
                    "first_offenders": missing[:5]},
    }


def check_combo_uniqueness(records, cfg, ref_records):
    reuse = Counter(combo_key(r, cfg) for r in records)
    worst = reuse.most_common(1)[0] if reuse else (None, 0)
    ref_keys = set()
    if ref_records:
        ref_keys = set(combo_key(r, cfg) for r in ref_records)
    collisions = sum(1 for r in records if combo_key(r, cfg) in ref_keys)
    limit = cfg["max_combo_reuse"]
    fails = []
    if worst[1] > max(limit, 1) and len(records) > 1:
        fails.append(f"one (entity, operation, mode) cell repeats {worst[1]}x (limit {limit})")
    if collisions:
        fails.append(f"{collisions} records reuse a cell already present in the accepted corpus")
    return {
        "pass": not fails,
        "detail": "; ".join(fails) or "every sample occupies a distinct grid cell",
        "metrics": {
            "distinct_cells": len(reuse),
            "worst_cell_reuse": worst[1],
            "worst_cell": " | ".join(f"{f}={v}" for _, f, v in worst[0]) if worst[0] else "",
            "reference_cell_collisions": collisions,
        },
    }


def check_label_swap(records, cfg, ref_records):
    """The exact failure mode the layer-9 pair exhibits: same entity+operation, only label differs."""
    groups = defaultdict(list)
    for i, r in enumerate(records):
        groups[entity_operation_key(r, cfg)].append(i)
    offenders = {key: idxs for key, idxs in groups.items() if len(idxs) > 1}
    ref_index = defaultdict(list)
    for r in ref_records:
        ref_index[entity_operation_key(r, cfg)].append(label_key(r, cfg))
    cross = 0
    for i, r in enumerate(records):
        key = entity_operation_key(r, cfg)
        if key in ref_index and any(lk != label_key(r, cfg) for lk in ref_index[key]):
            cross += 1
    within = sum(len(v) - 1 for v in offenders.values())
    detail = "no sample shares its entity+operation with any other sample"
    fails = []
    if within:
        fails.append(f"{within} samples share entity+operation with another sample in this batch")
    if cross:
        fails.append(f"{cross} samples share entity+operation with an accepted record but differ only by label")
    worst_example = ""
    if offenders:
        key, idxs = max(offenders.items(), key=lambda kv: len(kv[1]))
        sample = records[idxs[0]]
        worst_example = " ".join(f"{f}={v}" for _, f, v in key) + f" repeated {len(idxs)}x"
    return {
        "pass": not fails,
        "detail": "; ".join(fails) or detail,
        "metrics": {"within_batch_entity_operation_repeats": within,
                    "cross_reference_label_only_swaps": cross,
                    "worst_group": worst_example},
    }


MIN_BATCH_FOR_SHARES = 50


def check_template_diversity(records, cfg):
    if len(records) < MIN_BATCH_FOR_SHARES:
        return {"pass": True, "detail": f"batch smaller than {MIN_BATCH_FOR_SHARES}: share thresholds not meaningful",
                "metrics": {"records": len(records)}}
    extra = set()
    for r in records:
        for value in r.get("fingerprint", {}).values():
            if isinstance(value, str):
                extra.add(value.lower())
    signatures = Counter(template_signature(r, cfg, extra) for r in records)
    total = max(len(records), 1)
    distinct = len(signatures)
    top_share = signatures.most_common(1)[0][1] / total if signatures else 0.0
    distinct_frac = distinct / total
    fails = []
    if distinct_frac < cfg["min_template_fraction"]:
        fails.append(f"template diversity {distinct_frac:.0%} < required {cfg['min_template_fraction']:.0%}")
    if top_share > cfg["max_template_share"]:
        fails.append(f"single frame covers {top_share:.0%} of the batch > limit {cfg['max_template_share']:.0%}")
    worst = signatures.most_common(1)[0] if signatures else ("", 0)
    return {
        "pass": not fails,
        "detail": "; ".join(fails) or f"{distinct} distinct sentence frames",
        "metrics": {"distinct_templates": distinct,
                    "template_diversity": round(distinct_frac, 4),
                    "top_template_share": round(top_share, 4),
                    "top_template_excerpt": worst[0][:200],
                    "top_template_count": worst[1]},
    }


def check_pool_capacity(records, cfg):
    entities = set(slot(r, f, cfg) for r in records for f in cfg["entity_fields"])
    operations = set(slot(r, f, cfg) for r in records for f in cfg["operation_fields"])
    constraints = {f: set(slot(r, f, cfg) for r in records) for f in constraint_fields(cfg)}
    capacity = max(len(entities), 1) * max(len(operations), 1)
    for values in constraints.values():
        capacity *= max(len(values), 1)
    required = cfg.get("min_entity_pool", 0)
    fails = []
    if required and len(entities) < required:
        fails.append(f"entity pool {len(entities)} < required {required} for this layer's target")
    return {
        "pass": not fails,
        "detail": "; ".join(fails) or f"entity pool {len(entities)} meets requirement",
        "metrics": {"distinct_entities": len(entities), "distinct_operations": len(operations),
                    "distinct_constraints": {k: len(v) for k, v in constraints.items()},
                    "grid_capacity": capacity,
                    "required_entity_pool": required,
                    "batch_fills_grid": round(len(records) / capacity, 3) if capacity else None},
    }


def check_label_padding(records, cfg, cells):
    """How many records each distinct scenario cell carries. A cell repeated 10x with a
    different framework/runtime/stack label each time is padding, not data."""
    if len(records) < MIN_BATCH_FOR_SHARES:
        return {"pass": True, "detail": f"batch smaller than {MIN_BATCH_FOR_SHARES}: padding ratio not meaningful",
                "metrics": {"records": len(records)}}
    padding = len(records) / max(len(cells), 1)
    limit = cfg.get("max_label_padding_factor", 2.0)
    declared = cfg.get("declared_variant_axes", [])
    detail = f"{padding:.2f} records per scenario cell"
    if declared:
        detail += f" (declared variant axis: {', '.join(declared)})"
    if padding > limit:
        detail = (f"{padding:.2f} records per scenario cell > limit {limit:.2f}: "
                  f"the label axis is doing the padding, not the scenario")
    return {"pass": padding <= limit, "detail": detail,
            "metrics": {"records_per_cell": round(padding, 3),
                        "limit": limit, "declared_variant_axes": declared}}


def check_quarantine(records, cfg, burned_nouns):
    if not burned_nouns:
        return {"pass": True, "detail": "no quarantine pools configured", "metrics": {}}
    batch_entities = [slot(r, f, cfg) for r in records for f in cfg["entity_fields"]]
    batch_entities = [e for e in batch_entities if e]
    overlap = [e for e in batch_entities if e in burned_nouns]
    share = len(overlap) / max(len(batch_entities), 1)
    limit = cfg.get("max_quarantine_overlap", 0.20)
    return {
        "pass": share <= limit,
        "detail": (f"{share:.0%} of entity nouns already burned in other layers (limit {limit:.0%})"
                   if share > limit else f"noun quarantine ok ({share:.0%} overlap)"),
        "metrics": {"quarantine_overlap_share": round(share, 4),
                    "quarantined_pool_size": len(burned_nouns),
                    "overlapping_entities": sorted(set(overlap))[:25]},
    }


def load_quarantine_pool(config, patterns):
    """Entity nouns already consumed by other layers, extracted with each layer's own field names."""
    pool = set()
    for pattern in patterns or []:
        for path in sorted(glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]):
            match = re.search(r"layer(\d+)_", os.path.basename(path))
            ref_cfg = config["layers"].get(match.group(1)) if match else None
            if not ref_cfg:
                continue
            records, _ = load_jsonl([path])
            for record in records:
                for field in ref_cfg["entity_fields"]:
                    value = slot(record, field, ref_cfg)
                    if value:
                        pool.add(value)
    return pool


# -------------------------------------------------------------------- main ---

def audit(records, cfg, label, ref_records=None, burned_nouns=None,
          config=None, similarity=False):
    thresholds = dict(config["defaults"])
    thresholds.update({k: v for k, v in cfg.items() if k in thresholds})
    cfg = dict(cfg)
    cfg.update({k: thresholds[k] for k in thresholds if k not in cfg})
    ref_records = ref_records or []
    cells = Counter(combo_key(r, cfg) for r in records)
    checks = {
        "label_padding": check_label_padding(records, cfg, cells),
        "schema": check_schema(records, cfg),
        "tool_call_requirement": check_tool_calls(records, cfg),
        "combo_uniqueness": check_combo_uniqueness(records, cfg, ref_records),
        "entity_operation_uniqueness": check_label_swap(records, cfg, ref_records),
        "template_diversity": check_template_diversity(records, cfg),
        "pool_capacity": check_pool_capacity(records, cfg),
        "noun_quarantine": check_quarantine(records, cfg, burned_nouns or set()),
    }
    if similarity:
        result = similarity_conflicts(
            [user_message(r) for r in records],
            [user_message(r) for r in ref_records],
            cfg["similarity_threshold"], cfg["similarity_ngram"],
        )
        limit = cfg["max_cluster_share"]
        batch_share = result["samples_in_cluster_ge_10"] / max(len(records), 1)
        fails = []
        if batch_share > limit:
            fails.append(f"{batch_share:.0%} of the batch sits in char-{cfg['similarity_ngram']}gram clusters of 10+ (limit {limit:.0%})")
        if result["records_matching_reference"]:
            fails.append(f"{result['records_matching_reference']} records are char-ngram near-duplicates of accepted records")
        checks["char_ngram_similarity"] = {
            "pass": not fails, "detail": "; ".join(fails) or "no char-ngram near-duplicate mass",
            "metrics": result,
        }
    verdict = "PASS" if all(c["pass"] for c in checks.values()) else "FAIL"
    return {"label": label, "records": len(records), "reference_records": len(ref_records),
            "verdict": verdict, "checks": checks}


def print_report(report):
    print(f"\n=== {report['label']}  ({report['records']} records, "
          f"{report['reference_records']} accepted records as reference)  ->  {report['verdict']}")
    for name, check in report["checks"].items():
        mark = "PASS" if check["pass"] else "FAIL"
        print(f"  [{mark}] {name}: {check['detail']}")
        for key, value in check["metrics"].items():
            if isinstance(value, float):
                value = round(value, 4)
            if isinstance(value, str) and len(value) > 120:
                value = value[:120] + "..."
            print(f"          - {key}: {value}")


def layer_files(config, layer, kind="reference_files"):
    return config.get(kind, {}).get(str(layer), [])


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--layer", type=int, help="layer number 1-14")
    parser.add_argument("--input", nargs="+", help="batch file(s) or glob(s) to gate")
    parser.add_argument("--reference", nargs="*", help="accepted files to check conflicts against")
    parser.add_argument("--no-reference", action="store_true")
    parser.add_argument("--quarantine", nargs="*", help="override quarantine files")
    parser.add_argument("--no-quarantine", action="store_true")
    parser.add_argument("--similarity", action="store_true", help="run the char n-gram cluster check too")
    parser.add_argument("--all", action="store_true", help="gate every existing corpus file per layer")
    parser.add_argument("--json", help="write the full report as JSON")
    parser.add_argument("--config", default=CONFIG_PATH)
    args = parser.parse_args()

    config = load_config(args.config)
    reports = []

    if args.all:
        for key in sorted(config["layers"], key=int):
            files = layer_files(config, key, "reference_files")
            if not files:
                continue
            records, _ = load_jsonl(files)
            if not records:
                continue
            cfg = config["layers"][key]
            burned = load_quarantine_pool(config, layer_files(config, key, "quarantine_files"))
            report = audit(records, cfg, f"layer {key} {cfg['name']} (existing corpus)",
                           ref_records=[], burned_nouns=burned,
                           config=config, similarity=args.similarity)
            reports.append(report)
            print_report(report)
    else:
        if not args.layer or not args.input:
            parser.error("--layer and --input are required unless --all is used")
        key = str(args.layer)
        if key not in config["layers"]:
            parser.error(f"layer {key} not in config")
        cfg = config["layers"][key]
        records, files = load_jsonl(args.input)
        if not records:
            print(f"no records found in {args.input}", file=sys.stderr)
            return 2
        ref_records = []
        if not args.no_reference:
            ref_files = args.reference if args.reference else layer_files(config, key, "reference_files")
            ref_records, _ = load_jsonl(ref_files)
        burned = set()
        if not args.no_quarantine:
            q_files = args.quarantine if args.quarantine else layer_files(config, key, "quarantine_files")
            burned = load_quarantine_pool(config, q_files)
        report = audit(records, cfg, f"layer {key} {cfg['name']} <- {', '.join(files)}",
                       ref_records=ref_records, burned_nouns=burned,
                       config=config, similarity=args.similarity)
        reports.append(report)
        print_report(report)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(reports, fh, indent=2)
        print(f"\nwrote {args.json}")

    failed = [r for r in reports if r["verdict"] == "FAIL"]
    print(f"\n{len(reports) - len(failed)}/{len(reports)} batches pass the gate")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
