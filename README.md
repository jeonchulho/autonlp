# autonlp

`stanza` 기반으로 문장에서 `주어/동사/목적어` 골격과 조건(부가정보)을 추출하는 예제 프로젝트입니다.

지원 언어: `ko`, `en`, `ja`, `zh`, `fr`, `de`, `ar`

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

초기 실행 지연을 줄이려면(모델 사전 다운로드):

```bash
python scripts/preload_stanza_models.py
# 일부 언어만 받고 싶으면
python scripts/preload_stanza_models.py --langs ko,en
```

Makefile로도 실행 가능:

```bash
make preload-models
make demo-config
make check
```

`make demo`(내부적으로 `python run_demo.py`)는 루트의 `autonlp.config.json`이 있으면 자동으로 읽어 적용합니다.

## 빠른 실행

```bash
python run_demo.py "내일 서울에서 고객에게 이메일을 보내기 위해 자동화 도구로 보고서를 3건 전송해."
python run_demo.py --lang en "Send 3 reports to the customer in Seoul tomorrow using an automation tool."
python run_demo.py --lang ja "明日、ソウルで顧客に3件のレポートを自動化ツールで送信してください。"
python run_demo.py --lang zh "请在明天于首尔使用自动化工具向客户发送3份报告。"
python run_demo.py --lang fr "Envoyez 3 rapports au client à Séoul demain avec un outil d'automatisation."
python run_demo.py --lang de "Sende morgen in Seoul 3 Berichte mit einem Automatisierungstool an den Kunden."
python run_demo.py --lang ar "أرسل 3 تقارير إلى العميل في سيول غدًا باستخدام أداة أتمتة."
python run_demo.py --lang ko --ref-datetime 2026-03-04T12:00:00 "어제,오늘"
python run_demo.py --lang ko --recipient-lexicon-file recipients.txt "어제 이후로 전철호,이선정,영업팀에게 보낸 쪽지 알려줘."
python run_demo.py --lang en "Show revenue details and total revenue"
python run_demo.py --lang ko --disable-object-normalization "최근 7일 이대성이사가 매출 내역 및 총 매출 합계 알려줘"
python run_demo.py --lang ko --object-join-token " | " "최근 7일 이대성이사가 매출 내역 및 총 매출 합계 알려줘"
python run_demo.py --config-file autonlp.config.json --lang en "Show revenue details and total revenue"
```

## REST API 서버 (FastAPI)

서버 실행:

```bash
make run-api
# 또는
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

운영 환경 권장 변수:

```bash
export AUTONLP_API_KEYS="ak_xxx,ak_yyy"
export AUTONLP_AUTH_ISSUER_TOKEN="issuer-admin-token"
export AUTONLP_ISSUED_KEY_TTL_SECONDS=86400
export AUTONLP_RATE_LIMIT_WINDOW_SECONDS=60
export AUTONLP_RATE_LIMIT_MAX_REQUESTS=120
export AUTONLP_BATCH_MAX_ITEMS=32
```

`AUTONLP_API_TOKEN`도 계속 지원하지만, 신규 설정은 `AUTONLP_API_KEYS`(콤마 구분) 사용을 권장합니다.

auth key 생성 루틴(로컬):

```bash
make gen-auth-key
# 또는
python scripts/generate_auth_key.py --print-export
```

런타임 발급 루틴(API):

```bash
curl -X POST http://localhost:8000/auth/issue-key \
	-H "X-Issuer-Token: ${AUTONLP_AUTH_ISSUER_TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"ttl_seconds": 3600}'
```

API는 인증 키를 다음 헤더 중 하나로 수신해 검증합니다.

- `Authorization: Bearer <auth_key>`
- `X-Auth-Key: <auth_key>`

기본 엔드포인트:

- `GET /health`
- `GET /supported-langs`
- `POST /auth/issue-key`
- `POST /extract`
- `POST /extract/batch`

예시 요청:

```bash
curl -X POST http://localhost:8000/extract \
	-H "Authorization: Bearer ${AUTH_KEY}" \
	-H "Content-Type: application/json" \
	-d '{
		"text": "어제,오늘 전철호에게 보낸 쪽지 알려줘",
		"lang": "ko",
		"ref_datetime": "2026-03-04T12:00:00+09:00"
	}'
```

배치 요청 예시:

```bash
curl -X POST http://localhost:8000/extract/batch \
	-H "X-Auth-Key: ${AUTH_KEY}" \
	-H "Content-Type: application/json" \
	-d '{
		"continue_on_error": true,
		"items": [
			{"text":"어제 매출 알려줘","lang":"ko"},
			{"text":"Show yesterday revenue","lang":"en"}
		]
	}'
```

Swagger UI:

- `http://localhost:8000/docs`

`--recipient-lexicon-file`를 주면 파일(한 줄 1이름)에 포함된 수신자만 `RECIPIENT`로 남깁니다.
`object_items`는 언어별 연결어(ko: `및/와/과`, en: `and/or`, ja: `と/および`, zh: `和/及`, fr: `et/ou`, de: `und/oder`, ar: `و/أو`)와 기호(`/`, `·`, `,` 등)로 분리합니다.
`--object-join-token`을 주면 `object_normalized` 결합 구분자를 언어 기본값 대신 사용자 지정 문자열로 사용합니다.
지시어 목적어(예: `그내용`, `that content`, `その内容`, `那个内容`)는 문맥의 메시지 명사(`쪽지/message/メッセージ/消息` 등)로 다국어 보정합니다.

전역 설정 파일(`autonlp.config.json`) 또는 `--config-file`로도 기본 결합자를 지정할 수 있습니다.

```json
{
	"suppress_report_verbs_ko": false,
	"object_join_token": " | ",
	"object_join_token_by_lang": {
		"zh": "、",
		"ja": "・"
	}
}
```

`suppress_report_verbs_ko=true`로 설정하면 한국어 뉴스 문맥에서 `밝혔다/전했다/말했다` 같은 보도 서술어를 이벤트 동사가 있을 때 predicate 후보에서 제외합니다.
`suppress_report_verbs_en=true`로 설정하면 영어 뉴스 문맥에서 `said/stated/announced/reported` 같은 보도 서술어를 이벤트 동사가 있을 때 predicate 후보에서 제외합니다.
`suppress_report_verbs_fr=true`로 설정하면 프랑스어 뉴스 문맥에서 `déclaré/indiqué/annoncé/rapporté` 같은 보도 서술어를 이벤트 동사가 있을 때 predicate 후보에서 제외합니다.
`suppress_report_verbs_de=true`로 설정하면 독일어 뉴스 문맥에서 `sagte/erklärte/berichtete/meldete` 같은 보도 서술어를 이벤트 동사가 있을 때 predicate 후보에서 제외합니다.
`suppress_report_verbs_ar=true`로 설정하면 아랍어 뉴스 문맥에서 `قال/صرح/أعلن/ذكر` 같은 보도 서술어를 이벤트 동사가 있을 때 predicate 후보에서 제외합니다.

우선순위: `--object-join-token` > `object_join_token_by_lang` > `object_join_token` > 언어 기본값.

샘플 파일은 저장소 루트의 `autonlp.config.example.json`을 참고해 `autonlp.config.json`으로 복사해서 사용하면 됩니다.

## TIME 정규화 규칙 (MVP)

- 범위 표현은 반개구간 `[start, end)` 으로 저장
- 시간 문자열 포맷은 UTC 14자리 `YYYYMMDDHHMMSS`
- `어제` → `TIME_RANGE(어제 00:00 ~ 오늘 00:00)`
- `오늘` → `TIME_RANGE(오늘 00:00 ~ 내일 00:00)`
- `어제,오늘` → 2개의 `TIME_RANGE`로 분리
- `어제 이후로` → `TIME_RANGE(어제 00:00 ~ 내일 00:00)`
- `이날` / `당일` → `TIME_RANGE(기준시각의 당일 00:00 ~ 익일 00:00)`
- `최근 7일` → `TIME_RANGE(오늘 포함 7일)`
- `2026년 3월 4일` / `2026-03-04` → 하루 범위
- `내일 오전 10시` / `tomorrow 10am` 등 → `TIME_POINT`

한국어 VALUE fallback 패턴:

- `140여 명`, `수십 명`, `20여 척` 형태를 `VALUE`로 추출

모듈 위치: `autonlp/time_normalizer.py`

## RECIPIENT 패턴 예시

`extract_recipients_from_text()`는 언어별 전치사/조사 패턴 + 질의형 나열 패턴을 함께 사용합니다.

| 언어 | 명시 패턴 예시 | 질의형 나열 예시 |
|---|---|---|
| ko | `전철호,이선정에게 보낸 쪽지` | `전철호,이선정?` |
| en | `messages sent to alice,bob` / `for alice,bob` | `alice,bob?` |
| ja | `山田、佐藤に送ったメッセージ` | `山田,佐藤?` |
| zh | `给张三，李四发送的消息` / `向张三，李四` | `张三,李四?` |
| fr | `messages envoyés à alice,bob` / `pour alice,bob` | `alice,bob?` |
| de | `Nachrichten an alice,bob` / `für alice,bob` | `alice,bob?` |
| ar | `رسائل إلى علي،سارة` / `لـ علي،سارة` | `علي،سارة؟` |

모듈 위치: `autonlp/rules.py`

### 오탐 주의 케이스

- `zh`: `给张三，李四发送的消息...`처럼 동사가 바로 붙으면 이름 span이 길어질 수 있음
- `ar`: `ل` 단일 접두사 패턴은 의미 범위가 넓어 오탐 가능성이 높아, 현재는 `إلى`/`لـ` 중심으로 제한
- `ja`: `に`는 장소/방향 의미도 많아 수신자와 LOC가 문맥에 따라 충돌 가능
- `fr/de`: `pour`/`für`는 목적(PURPOSE) 의미로도 자주 쓰여 RECIPIENT와 경합 가능
- `en`: `for`는 수신자/목적 양쪽으로 쓰이므로 후속 LLM/SRL 보강 단계 권장

완화 팁:

- 이름 사전(직원/조직)과 대조해 후보를 필터링
- 문장 내 동사 프레임(`send`, `notify`, `message` 등) 기반 후처리 추가
- `confidence` 임계값을 언어별로 분리 적용

## 골든 샘플 평가

언어별(ko/en/ja/zh/fr/de/ar) 골든 샘플(각 7개)로 정규화 precision/recall/f1을 계산합니다.

```bash
python evaluation/evaluate_time_normalization.py
```

샘플 데이터: `evaluation/golden_time_samples.py`

타임존 포함 기준시각 변환 검증:

```bash
python evaluation/evaluate_timezone_conversion.py
```

복합 문장 predicate 분리(다국어) 검증:

```bash
python scripts/run_predicate_eval_batches.py
# 일부 언어만 검증
python evaluation/evaluate_predicate_split.py --langs ko,en
```

위 평가는 predicate뿐 아니라 predicate별 object 일치도(`obj_exact`, `obj_p/r/f1`)도 함께 출력합니다.

전체 추출 품질(다국어) 회귀 평가(predicate/subject/object/conditions):

```bash
python scripts/run_extraction_eval_batches.py
# 일부 언어만 검증
python evaluation/evaluate_extraction_quality.py --langs ko,en
```

익명 샘플 로그에서 오탐/누락 후보 수집:

```bash
# 샘플 입력 사용
make collect-cases

# 직접 파일 지정
python scripts/collect_error_cases.py \
	--input evaluation/anonymized_cases.sample.jsonl \
	--output evaluation/error_case_report.jsonl \
	--ref-datetime 2026-03-04T12:00:00+09:00 \
	--langs ko,en
```

`make collect-cases`는 언어 배치(ko/en, ja/zh, fr/de, ar)로 분할 실행한 뒤 `evaluation/error_case_report.jsonl`로 합칩니다.

입력 JSONL 각 줄 예시:

```json
{"lang":"ko","text":"어제,오늘 전철호에게 보낸 쪽지 알려줘","expected_predicates":["알려줘"],"expected_objects":["쪽지"]}
```

## 실데이터 기반 오프라인 평가셋 + KPI

실사용 로그(익명화) + 뉴스 + 복합 질의를 합친 오프라인 평가셋을 제공합니다.

- 데이터셋: `evaluation/offline_eval_dataset.v1.jsonl`
- KPI 타깃: `evaluation/kpi_targets.v1.json`
- 평가 스크립트: `evaluation/evaluate_offline_kpi.py`

### 데이터셋 필드

- `source`: `anonymized_real|curated_golden|news_wire`
- `domain`: `ops_log|assistant_query|news`
- `lang`: `ko|en|ja|zh|fr|de|ar`
- `length`: `short|medium|long`
- `noise`: `clean|typo_punct`
- `text`: 입력 문장
- `expected_predicates` / `expected_objects`: 시퀀스 정합 지표용(선택)

### KPI 지표(기본)

- `predicate_seq_acc`
- `object_seq_acc`
- `time_hint_coverage`
- `recipient_hint_coverage`
- `runtime_error_rate`

슬라이스(`lang/domain/length/noise`)별 최소 샘플 수(`min_cases`)를 넘는 그룹에 대해
`predicate_seq_acc`와 `runtime_error_rate`를 함께 게이트합니다.

### 실행

```bash
python evaluation/evaluate_offline_kpi.py \
	--dataset evaluation/offline_eval_dataset.v1.jsonl \
	--kpi evaluation/kpi_targets.v1.json

# 또는
make eval-offline-kpi
```

### v2 확장셋 (언어별 ops_log 10건+)

`v2`는 `ops_log`를 언어별 10건 이상으로 늘려 슬라이스 평가의 `SKIP`를 줄인 버전입니다.

- 생성 스크립트: `scripts/generate_offline_dataset_v2.py`
- 결과 데이터셋: `evaluation/offline_eval_dataset.v2.jsonl`
- KPI 타깃: `evaluation/kpi_targets.v2.json`

```bash
python scripts/generate_offline_dataset_v2.py
python scripts/run_offline_kpi_batches.py \
	--dataset evaluation/offline_eval_dataset.v2.jsonl \
	--kpi evaluation/kpi_targets.v2.json

# 또는
make eval-offline-kpi-v2
```

## 출력 스키마

```json
{
	"text": "원문",
	"sentences": [
		{
			"text": "문장",
			"predicate": "동사",
			"subject": "주어",
			"object": "목적어",
			"object_normalized": "정규화된 목적어 문자열",
			"object_items": ["목적어1", "목적어2"],
			"recipients": ["수신자1", "수신자2"],
			"conditions": [
				{
					"label": "TIME|DURATION|LOC|RECIPIENT|PURPOSE|METHOD|VALUE|POLARITY|UNKNOWN",
					"text": "조건 span",
					"value": "정규화 값(선택)",
					"confidence": 0.0,
					"source": "rule|srl|llm"
				}
			]
		}
	]
}
```

## 설계 포인트

- 1층: `stanza`로 토큰/품사/의존구문/NER 분석
- 2층: 규칙 기반으로 조건 후보 수집 + 라벨링
- 3층: SRL 결과 병합 + 애매한 후보를 LLM으로 보강(옵션)

일부 언어/환경에서 `stanza` `ner` 모델이 비활성일 수 있어, 이 프로젝트는 자동으로 `depparse` 중심 모드로 폴백합니다.

## 파일 구조

- `autonlp/pipeline.py`: 전체 파이프라인
- `autonlp/rules.py`: 조건 후보/라벨 규칙
- `autonlp/srl.py`: SRL 인터페이스
- `autonlp/llm.py`: LLM 라벨러 인터페이스
- `run_demo.py`: CLI 실행 예제