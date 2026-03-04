from __future__ import annotations

import argparse
import subprocess
import sys


LANGS = ["ko", "en", "ja", "zh", "fr", "de", "ar"]


def run_lang(lang: str, dataset: str, kpi: str, ref_datetime: str) -> int:
    command = [
        sys.executable,
        "evaluation/evaluate_offline_kpi.py",
        "--dataset",
        dataset,
        "--kpi",
        kpi,
        "--ref-datetime",
        ref_datetime,
        "--langs",
        lang,
    ]
    print(f"== Running offline KPI batch: {lang} ==")
    completed = subprocess.run(command)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/offline_eval_dataset.v1.jsonl")
    parser.add_argument("--kpi", default="evaluation/kpi_targets.v1.json")
    parser.add_argument("--ref-datetime", default="2026-03-04T12:00:00+09:00")
    args = parser.parse_args()

    failed: list[tuple[str, int]] = []
    for lang in LANGS:
        return_code = run_lang(lang, args.dataset, args.kpi, args.ref_datetime)
        if return_code != 0:
            failed.append((lang, return_code))

    if failed:
        print("\nBatches failed:")
        for lang, return_code in failed:
            print(f"- {lang} (exit={return_code})")
        raise SystemExit(1)

    print("\nAll offline KPI batches completed successfully.")


if __name__ == "__main__":
    main()
