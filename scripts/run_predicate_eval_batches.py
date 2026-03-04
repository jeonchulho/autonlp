from __future__ import annotations

import subprocess
import sys


BATCHES = [
    ["ko", "en"],
    ["ja", "zh"],
    ["fr", "de"],
    ["ar"],
]


def run_batch(langs: list[str]) -> int:
    lang_arg = ",".join(langs)
    command = [sys.executable, "evaluation/evaluate_predicate_split.py", "--langs", lang_arg]
    print(f"== Running predicate eval batch: {lang_arg} ==")
    completed = subprocess.run(command)
    return completed.returncode


def main() -> None:
    failed = []
    for langs in BATCHES:
        return_code = run_batch(langs)
        if return_code != 0:
            failed.append((langs, return_code))

    if failed:
        print("\nBatches failed:")
        for langs, return_code in failed:
            print(f"- {','.join(langs)} (exit={return_code})")
        raise SystemExit(1)

    print("\nAll predicate eval batches completed successfully.")


if __name__ == "__main__":
    main()
