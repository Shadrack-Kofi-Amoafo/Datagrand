#!/usr/bin/env python3
"""Threshold-free duplication forensics for the 14-layer dataset.

The numbers this prints do not depend on any similarity threshold, which is the
point: the previous audit's verdict flipped depending on which vectorizer and
threshold you picked. These metrics are exact counts over the corpus:

  frames     distinct user-message signatures with every fingerprint value masked
             ("Build a round-trip for `React...` and `accounts`" and
              "Build a round-trip for `Vue...` and `accounts`" -> one frame)
  cells      distinct (entity, operation, mode) scenario cells, using the field
             map in pregen_gate_config.json
  redundant  records occupying a cell another record in the same layer already
             occupies -> padding, by construction

Usage:
  python3 audit_reports/duplication_forensics.py
  python3 audit_reports/duplication_forensics.py --json audit_reports/duplication_forensics.json \
                                                 --markdown audit_reports/duplication_forensics.md
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pregen_dup_gate as gate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = gate.load_config(os.path.join(HERE, "pregen_gate_config.json"))

BATCH_FILES = {
    1: ["data/layer1_final_1200.jsonl"],
    2: sorted(glob.glob("data/layer2_batch*.jsonl")),
    3: sorted(glob.glob("data/layer3_batch*.jsonl")),
    4: ["data/layer4_samples_5.jsonl"],
}
for layer in range(5, 15):
    matches = sorted(glob.glob(f"data/layer{layer}_all_*.jsonl"))
    if matches:
        BATCH_FILES[layer] = matches


def load(paths):
    records = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]):
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                continue
            with open(path) as fh:
                records += [json.loads(line) for line in fh if line.strip()]
    return records


def masked_frame_counts(records, cfg):
    """Sentence frames with every fingerprint value, backticked slot and tree/code line
    masked: identical wording with a swapped noun/stack must collapse to one frame."""
    return Counter(gate.template_signature(r, cfg) for r in records)


BASE_PROBLEM_RE = re.compile(r"^(typescript|python|javascript|go|java|ruby|php)_")


def declared_content_note(layer, records):
    """Layers whose real content unit is narrower than frames x cells."""
    if layer == 3:
        problems = set(BASE_PROBLEM_RE.sub("", r["fingerprint"].get("problem_id", "")) for r in records)
        languages = set(r["fingerprint"].get("language", "") for r in records)
        return (len(problems), f"effective distinct content = {len(problems)} problem specs x "
                               f"{len(languages)} declared language implementations")
    if layer == 2:
        pairs = set((gate.extract_symbol(r), gate.slot(r, "task_type", CONFIG["layers"]["2"])) for r in records)
        symbols = set(gate.extract_symbol(r) for r in records)
        return (len(pairs), f"effective distinct content = {len(pairs)} (symbol x task_type) units "
                            f"from {len(symbols)} distinct symbols; depths 1-5 restate the same unit")
    return (None, "")


def analyse_layer(layer):
    cfg = CONFIG["layers"][str(layer)]
    paths = BATCH_FILES.get(layer, [])
    records = load(paths)
    if not records:
        return None
    frames = masked_frame_counts(records, cfg)
    cells = Counter(gate.combo_key(r, cfg) for r in records)
    entity_ops = Counter(gate.entity_operation_key(r, cfg) for r in records)
    labels = Counter(gate.label_key(r, cfg) for r in records)
    entities = set(gate.slot(r, f, cfg) for r in records for f in cfg["entity_fields"])
    raw = len(records)
    worst_cell = cells.most_common(1)[0] if cells else ((), 0)
    worst_frame = frames.most_common(1)[0] if frames else ("", 0)
    worst_entity_op = entity_ops.most_common(1)[0] if entity_ops else ((), 0)
    return {
        "layer": layer,
        "name": cfg["name"],
        "target": cfg["target"],
        "files": paths,
        "raw": raw,
        "distinct_frames": len(frames),
        "frame_diversity": round(len(frames) / raw, 4),
        "worst_frame_count": worst_frame[1],
        "worst_frame_share": round(worst_frame[1] / raw, 4),
        "worst_frame_excerpt": worst_frame[0][:220],
        "distinct_cells": len(cells),
        "worst_cell_reuse": worst_cell[1],
        "worst_cell": " | ".join(f"{f}={v}" for _, f, v in worst_cell[0]) if worst_cell[0] else "",
        "distinct_entity_operation_pairs": len(entity_ops),
        "worst_entity_operation_reuse": worst_entity_op[1],
        "worst_entity_operation": " ".join(f"{f}={v}" for _, f, v in worst_entity_op[0]) if worst_entity_op[0] else "",
        "distinct_entity_nouns": len(entities),
        "distinct_label_combos": len(labels),
        "redundant_records": raw - len(cells),
        "redundant_share": round((raw - len(cells)) / raw, 4),
        "label_padding_factor": round(raw / len(cells), 2) if cells else None,
        "effective_content_upper_bound": min(len(frames), len(cells)),
        "declared_content_bound": declared_content_note(layer, records)[0],
        "declared_content_note": declared_content_note(layer, records)[1],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="write raw metrics JSON")
    parser.add_argument("--markdown", help="write a markdown table")
    parser.add_argument("--layers", help="comma separated subset, default all")
    args = parser.parse_args()

    layers = [int(x) for x in args.layers.split(",")] if args.layers else sorted(BATCH_FILES)
    results = [r for r in (analyse_layer(l) for l in layers) if r]

    header = (f"{'L':>2} {'layer':<18}{'raw':>6}{'frames':>8}{'worst_frame':>12}"
              f"{'cells':>7}{'worst_cell':>11}{'ent*op':>7}{'redundant':>10}{'padding':>8}{'upper':>7}")
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['layer']:>2} {r['name']:<18}{r['raw']:>6}{r['distinct_frames']:>8}"
              f"{r['worst_frame_count']:>12}{r['distinct_cells']:>7}{r['worst_cell_reuse']:>11}"
              f"{r['distinct_entity_operation_pairs']:>7}{r['redundant_records']:>10}"
              f"{r['label_padding_factor']:>8}{r['effective_content_upper_bound']:>7}")
    total_raw = sum(r["raw"] for r in results)
    total_redundant = sum(r["redundant_records"] for r in results)
    print(f"\nraw records analysed: {total_raw}")
    print(f"records sitting in a scenario cell that another record in the same layer already occupies: "
          f"{total_redundant} ({total_redundant / total_raw:.1%})")
    print(f"sum of per-layer distinct scenario cells: {sum(r['distinct_cells'] for r in results)}")
    print(f"sum of per-layer distinct sentence frames: {sum(r['distinct_frames'] for r in results)}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
        print(f"wrote {args.json}")

    if args.markdown:
        lines = ["| Layer | Raw | Distinct frames | Worst frame | Distinct cells (entity x operation x constraint) "
                 "| Worst cell reuse | Redundant records | Label padding factor |",
                 "|---|---|---|---|---|---|---|---|"]
        for r in results:
            lines.append(
                f"| {r['layer']} {r['name']} | {r['raw']} | {r['distinct_frames']} | "
                f"{r['worst_frame_count']} ({r['worst_frame_share']:.0%}) | {r['distinct_cells']} | "
                f"{r['worst_cell_reuse']}x | {r['redundant_records']} ({r['redundant_share']:.0%}) | "
                f"{r['label_padding_factor']}x |")
        lines.append(
            f"| **Total** | **{total_raw}** | {sum(r['distinct_frames'] for r in results)} | | "
            f"**{sum(r['distinct_cells'] for r in results)}** | | "
            f"**{total_redundant} ({total_redundant / total_raw:.0%})** | |")
        with open(args.markdown, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"wrote {args.markdown}")


if __name__ == "__main__":
    main()
