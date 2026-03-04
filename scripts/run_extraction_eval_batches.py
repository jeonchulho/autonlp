from __future__ import annotations

import subprocess
import sys


BATCHES = [
    ["ko"],
    ["en"],
    ["ja"],
    ["zh"],
    ["fr"],
    ["de"],
    ["ar"],
]


def run_batch(langs: list[str]) -> int:
    lang_arg = ",".join(langs)
    command = [sys.executable, "evaluation/evaluate_extraction_quality.py", "--langs", lang_arg]
    print(f"== Running extraction eval batch: {lang_arg} ==")
    completed = subprocess.run(command)

    retries = 0
    while completed.returncode == -15 and retries < 2:
        retries += 1
        print(f"== Batch {lang_arg} terminated (SIGTERM). Retry {retries}/2 ==")
        completed = subprocess.run(command)

    if completed.returncode == -15 and len(langs) > 1:
        print(f"== Batch {lang_arg} terminated (SIGTERM). Retrying per-language ==")
        for lang in langs:
            retry_command = [sys.executable, "evaluation/evaluate_extraction_quality.py", "--langs", lang]
            retry_completed = subprocess.run(retry_command)
            if retry_completed.returncode != 0:
                return retry_completed.returncode
        return 0
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

    print("\nAll extraction eval batches completed successfully.")


if __name__ == "__main__":
    main()
