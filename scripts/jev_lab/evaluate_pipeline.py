#!/usr/bin/env python3
"""Compare externally adjudicated A/B/C runs, retaining failures in denominators.

Input JSONL: case_id, repeat, arm (A/B/C), accepted (external oracle), elapsed_ms,
human_minutes, cost_usd, false_closure. Does not execute agents or fabricate runs.
"""

import argparse
import json
import math
from pathlib import Path
from statistics import median


def evaluate(rows):
    indexed = {}
    for row in rows:
        if (
            row["arm"] not in {"A", "B", "C"}
            or type(row["accepted"]) is not bool
            or type(row["false_closure"]) is not bool
        ):
            raise ValueError("Invalid arm or external verdict")
        key = (row["case_id"], row["repeat"], row["arm"])
        if key in indexed:
            raise ValueError("Duplicate run")
        for field in ("elapsed_ms", "human_minutes", "cost_usd"):
            if (
                type(row[field]) not in (int, float)
                or not math.isfinite(row[field])
                or row[field] < 0
            ):
                raise ValueError("Invalid metric")
        indexed[key] = row
    pairs = {(case, repeat) for case, repeat, _ in indexed}
    if any(
        any((case, repeat, arm) not in indexed for arm in "ABC")
        for case, repeat in pairs
    ):
        raise ValueError(
            "All A/B/C observations, including failures, are required for each pair"
        )
    summary = {}
    for arm in "ABC":
        runs = [row for row in rows if row["arm"] == arm]
        summary[arm] = {
            "runs": len(runs),
            "accepted": sum(r["accepted"] for r in runs),
            "false_closures": sum(r["false_closure"] for r in runs),
            "elapsed_ms_total": sum(r["elapsed_ms"] for r in runs),
            "human_minutes_total": sum(r["human_minutes"] for r in runs),
            "cost_usd_total": sum(r["cost_usd"] for r in runs),
        }
    comparisons = {}
    for before, after in [("A", "B"), ("B", "C")]:
        ratios = {}
        for metric in ("elapsed_ms", "human_minutes", "cost_usd"):
            per_case = []
            for case in sorted({c for c, _ in pairs}):
                old = sum(indexed[c, r, before][metric] for c, r in pairs if c == case)
                new = sum(indexed[c, r, after][metric] for c, r in pairs if c == case)
                if old > 0:
                    per_case.append(new / old)
            ratios[metric] = {
                "median_case_ratio": median(per_case) if per_case else None,
                "cases_with_nonzero_baseline": len(per_case),
            }
        comparisons[f"{after}_vs_{before}"] = ratios
    enough = len({c for c, _ in pairs}) >= 12 and all(
        sum(c == case for c, _ in pairs) >= 3 for case, _ in pairs
    )
    quality = (
        summary["C"]["false_closures"] == 0
        and summary["C"]["accepted"] >= summary["B"]["accepted"]
    )
    time_ratio = comparisons["C_vs_B"]["elapsed_ms"]["median_case_ratio"]
    human_ratio = comparisons["C_vs_B"]["human_minutes"]["median_case_ratio"]
    benefit = (time_ratio is not None and time_ratio <= 0.8) or (
        human_ratio is not None and human_ratio <= 0.75
    )
    verdict = (
        "stop_false_closure"
        if summary["C"]["false_closures"]
        else "inconclusive"
        if not enough
        else "candidate_for_shadow_trial"
        if quality and benefit
        else "benefit_not_established"
    )
    return {
        "schema": "nienfos.pipeline-comparison/v1",
        "arms": summary,
        "comparisons": comparisons,
        "verdict": verdict,
        "caveat": "Observational pilot summary, not a significance test or causal guarantee. Repetitions are grouped by case. Failed runs remain counted; acceptance rate must accompany timing.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        [
            json.loads(line)
            for line in args.input.read_text().splitlines()
            if line.strip()
        ]
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verdict": result["verdict"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
