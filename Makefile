.PHONY: help install preload-models demo-config demo run-api gen-auth-key eval-time eval-tz eval-predicate eval-extraction eval-offline-kpi eval-offline-kpi-v2 collect-cases check

help:
	@echo "Targets:"
	@echo "  make install           # pip install -r requirements.txt"
	@echo "  make preload-models    # preload stanza models for default langs"
	@echo "  make demo-config       # create autonlp.config.json from example"
	@echo "  make demo              # run demo with default text"
	@echo "  make run-api           # run FastAPI server (uvicorn)"
	@echo "  make gen-auth-key      # generate API auth key"
	@echo "  make eval-time         # run multilingual time normalization eval"
	@echo "  make eval-tz           # run timezone conversion eval"
	@echo "  make eval-predicate    # run multilingual predicate split eval"
	@echo "  make eval-extraction   # run full extraction quality eval (pred/subj/obj/conditions)"
	@echo "  make eval-offline-kpi  # run expanded offline dataset KPI evaluation"
	@echo "  make eval-offline-kpi-v2 # run v2 offline dataset KPI evaluation"
	@echo "  make collect-cases     # run issue collector for anonymized jsonl cases"
	@echo "  make check             # compile checks + all evals"

install:
	pip install -r requirements.txt

preload-models:
	python scripts/preload_stanza_models.py

demo-config:
	cp --update=none autonlp.config.example.json autonlp.config.json || true
	@echo "autonlp.config.json is ready (existing file kept if already present)."

demo:
	python run_demo.py

run-api:
	uvicorn api.main:app --host 0.0.0.0 --port 8000

gen-auth-key:
	python scripts/generate_auth_key.py --print-export

eval-time:
	python evaluation/evaluate_time_normalization.py

eval-tz:
	python evaluation/evaluate_timezone_conversion.py

eval-predicate:
	python scripts/run_predicate_eval_batches.py

eval-extraction:
	python scripts/run_extraction_eval_batches.py

eval-offline-kpi:
	python scripts/run_offline_kpi_batches.py

eval-offline-kpi-v2:
	python scripts/generate_offline_dataset_v2.py
	python scripts/run_offline_kpi_batches.py --dataset evaluation/offline_eval_dataset.v2.jsonl --kpi evaluation/kpi_targets.v2.json

collect-cases:
	python scripts/collect_error_cases.py --input evaluation/anonymized_cases.sample.jsonl --output /tmp/error_case_ko_en.jsonl --langs ko,en --ref-datetime 2026-03-04T12:00:00+09:00
	python scripts/collect_error_cases.py --input evaluation/anonymized_cases.sample.jsonl --output /tmp/error_case_ja_zh.jsonl --langs ja,zh --ref-datetime 2026-03-04T12:00:00+09:00
	python scripts/collect_error_cases.py --input evaluation/anonymized_cases.sample.jsonl --output /tmp/error_case_fr_de.jsonl --langs fr,de --ref-datetime 2026-03-04T12:00:00+09:00
	python scripts/collect_error_cases.py --input evaluation/anonymized_cases.sample.jsonl --output /tmp/error_case_ar.jsonl --langs ar --ref-datetime 2026-03-04T12:00:00+09:00
	cat /tmp/error_case_ko_en.jsonl /tmp/error_case_ja_zh.jsonl /tmp/error_case_fr_de.jsonl /tmp/error_case_ar.jsonl > evaluation/error_case_report.jsonl

check:
	python -m py_compile autonlp/*.py evaluation/*.py run_demo.py scripts/*.py
	python evaluation/evaluate_timezone_conversion.py
	python evaluation/evaluate_time_normalization.py
	python scripts/run_predicate_eval_batches.py
	python scripts/run_extraction_eval_batches.py
	python scripts/run_offline_kpi_batches.py