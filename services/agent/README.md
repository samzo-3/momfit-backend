# AI 에이전트 — 오늘의 운동 리포트

운동을 끝낼 때 '오늘의 운동 리포트'를 만드는 에이전트다. 사실(날짜별 횟수와 점수)은 항상 코드가
팀 테이블에서 계산하고, 문장만 LLM이 쓴다.

## 폴더 지도

팀 README의 계층 구조(`api/` → `services/` → `repositories/`, `schemas/`, `models/`)를 따르되,
계층마다 `agent/` 하위 폴더를 만들어 에이전트 파일은 모두 그 안에 둔다. 팀 폴더 바로 아래에는
에이전트 파일을 두지 않는다.

| 계층 | 파일 | 역할 |
| --- | --- | --- |
| `api/agent/` | `daily_report.py` | `POST /api/agent/daily-report` |
| `schemas/agent/` | `daily_report.py` | 요청·응답 형식 |
| `models/agent/` | `agent_feedback.py` | `agent_feedback` 테이블 (에이전트의 유일한 쓰기 대상) |
| `repositories/agent/` | `agent_feedback_repository.py` | STEP 메모·DAILY 저장과 조회 |
| `repositories/agent/` | `team_activity_reader.py` | 팀 운동 기록 읽기 전용 (SQL / fixture) |
| `services/agent/` | `config.py` | `AGENT_*` 환경변수, 팀 코드에서 가져온 상수(develop #15 기준), 프롬프트·규칙 로더 |
| `services/agent/` | `report_stats.py` | 집계·후보 고르기·`is_comparable` (순수 함수) |
| `services/agent/` | `step_memory.py` | STEP 기억 쓰기 (`update_step_memory`, 따라잡기) |
| `services/agent/` | `daily_report.py` | DAILY 기억 꺼내기 (처리 순서 8단계) |
| `services/agent/` | `output_check.py` | JSON 형식·금지어·건강 단어·길이·후보 검사 |
| `services/agent/` | `llm.py` | mock / gemini / anthropic 제공자 |
| `services/agent/` | `prompts/`, `rules/`, `fixtures/`, `runs/` | 프롬프트, 규칙 파일, 가짜 기록, 실행 기록 |
| `scripts/agent/` | `run_scenarios.py` | 시나리오 실행기 |
| `tests/agent/` | `test_agent_*.py` | 테스트 (팀 `tests/conftest.py`를 그대로 쓴다) |

팀 파일에서 바뀐 것은 몇 줄뿐이다: `main.py`(라우터 등록 2줄), `models/__init__.py`(모델 import),
`requirements.txt`(`google-genai`, `anthropic`), `.env.example`·`compose.yaml`(`AGENT_*` 환경변수).
`agent_feedback.exercise_step_records_id`는 팀의 `exercise_step_records`를 FK로 가리키므로,
`models/agent/agent_feedback.py`가 팀 모델 3개(`exercise`, `exercise_step`, `exercise_step_record`)를
import한다. `main.py`를 거치지 않는 `run_scenarios.py`에서도 `create_all`이 실패하지 않게 하기 위해서다.

## 두 단계

| 단계 | 언제 | 무엇을 | 사용자에게 |
| --- | --- | --- | --- |
| STEP (기억 쓰기) | 스텝 기록이 저장될 때마다 | 그 스텝의 '오늘 메모' 하나를 다시 써서 저장 | 보여 주지 않음 |
| DAILY (기억 꺼내기) | 리포트를 요청할 때 | 오늘 숫자 + STEP 메모로 한마디와 다음 집중 스텝 | 보여 줌 |

STEP 메모는 빠지거나 늦을 수 있는 요약본이다. 그래서 리포트는 먼저 팀 테이블에서 숫자를 다시
계산하고, 메모가 낡은 스텝만 '따라잡기'로 갱신한 뒤 DAILY를 쓴다.

BE가 스텝 기록을 저장한 직후에 한 줄만 넣으면 STEP 단계가 붙는다.

```python
background_tasks.add_task(update_step_memory, record.id)
```

## 경계

- fixture 모드(가짜 기록)는 `agent_feedback`을 읽지도 쓰지도 않는다. 가짜 기록으로 만든 메모·리포트가
  실제 사용자 계정에 쌓이지 않게 하고, STEP 메모의 FK가 DB에 없는 가짜 기록 번호를 가리켜 MySQL이
  거부하는 일을 막는다. 그래서 fixture 모드에서는 요청마다 STEP 메모를 새로 만든다.
- 팀 테이블은 읽기만 한다. 쓰기는 `agent_feedback` 하나뿐이다. 읽는 팀 테이블은 `exercises`,
  `exercise_steps`, `exercise_records`, `exercise_step_records`, `voice_cues`다.
- 일반 운동 점수(`exercise_records.total_score`)는 자세 점수가 아니라 '완료 세트 × 세트당 점수'다.
  리포트는 '완료 세트 / 목표 세트'로 보여 준다. 완료 세트는 `exercise_records.completed_sets`,
  목표 세트는 팀 점수 규칙(`services/exercise_scoring_config.py`)에서 읽는다. LLM에는 일반 운동
  점수를 자세 평가처럼 말하지 말라고 한다. (`prompts/daily_system.md`)
- 스텝 통과 횟수는 `exercise_step_records.status`(PASS, 80점 이상)로 센다. STEP 메모에 LLM을
  부를지는 지금처럼 `step_report`의 CV 판정과 피드백 코드로 정한다.
- 숫자와 판정은 코드가, 문장은 LLM이 쓴다. 무엇을 기억할지와 다음 집중 스텝 후보도 코드가 정한다.
- 원인은 CV가 감지한 피드백 코드만 말한다. 코드가 없으면 원인을 말하지 않는다.
- 건강·증상·감정은 기억하지도 말하지도 않는다. (`rules/health_terms.json`)
- 관절 수치(`measured_metrics`, `metric_results`)는 읽는 경계에서 버린다. LLM에 보낼 것이 없다.
- 에이전트가 실패해도 팀 서버는 멈추지 않는다. 운동 기록 테이블이 없으면 이 API만 503이고,
  LLM이 실패하면 숫자로 채운 대체 문장을 돌려준다.

## 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `AGENT_DATA_SOURCE` | `fixture` | `fixture`=가짜 기록, `db`=팀 테이블 |
| `AGENT_FIXTURE_SCENARIO` | `evaluated` | `fixtures/scenario_{이름}.json` |
| `AGENT_LLM_PROVIDER` | `mock` | `mock` / `gemini` / `anthropic` |
| `AGENT_LLM_MODEL` | (빈값) | 비우면 제공자별 기본 모델 |
| `AGENT_LLM_TIMEOUT_SECONDS` | `10` | 호출 하나의 제한 시간 |
| `AGENT_REPORT_TIMEOUT_SECONDS` | `25` | 리포트 하나의 전체 제한 시간 |
| `AGENT_APP_ENV` | `dev` | `prod`면 허용 제공자만 쓴다 |
| `AGENT_PROD_PROVIDERS` | `anthropic` | 운영에서 허용하는 제공자 |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | (빈값) | 쓰는 제공자의 키만 채운다 |

## 실행

```bash
uvicorn main:app --reload                 # 서버
pytest                                    # 전체 테스트
pytest tests/agent                        # 에이전트 테스트만
python -m scripts.agent.run_scenarios     # 시나리오 비교표 + 실행 기록
```

팀 DB는 MySQL이다. 에이전트 테스트는 SQLite에서도 FK 검사를 켜고 돈다(`tests/agent/conftest.py`).
실제 MySQL로 돌리려면 팀 `tests/conftest.py`의 `TEST_DATABASE_URL`을 쓴다. 이 DB의 테이블은 테스트마다
지워지므로 비어 있는 테스트 전용 DB를 쓴다.

```bash
TEST_DATABASE_URL="mysql+pymysql://root:비밀번호@127.0.0.1:3307/momfit_test?charset=utf8mb4" pytest
```

`runs/`에는 `run_scenarios` 실행 기록이 쌓인다. 프롬프트나 모델을 바꾼 전후를 비교할 때 쓰고,
남길 가치가 있는 기록만 골라서 커밋한다. (provider, model, 프롬프트 버전, latency_ms, 토큰 수는
DB에 저장하지 않고 이 파일에만 남는다)

## LLM 제공자 결정

**개발: Gemini 무료 등급 (`gemini-3.8-flash`)**
무료 등급은 요금이 들지 않는 대신 입력·출력이 구글 제품 개선에 쓰일 수 있다. 그래서 개발 중에는
`services/agent/fixtures/`의 가짜 데이터만 넣는다. 실제 사용자 기록은 넣지 않는다.
(유료 등급은 제품 개선에 쓰지 않는다고 적혀 있다.)

**실제 사용자 데이터가 들어가기 전: Claude API (`claude-haiku-5-5`)**

| 항목 | 값 |
| --- | --- |
| 모델 ID | `claude-haiku-5-5` |
| 입력 / 출력 (프롬프트 10만 토큰 이하) | $0.10 / $0.50 per MTok |
| 입력 / 출력 (프롬프트 10만 토큰 초과) | $0.50 / $2.50 per MTok |
| 캐시 히트 (10만 토큰 이하) | $0.01 per MTok |
| 컨텍스트 / 최대 출력 | 1M / 128K 토큰 |

바꾸는 이유는 세 가지다.

1. **데이터**: 상용 API로 보낸 입력·출력은 별도 합의가 없으면 모델 학습에 쓰지 않는다.
2. **단가**: 리포트 한 건은 입력 수천 토큰, 출력 수백 토큰이라 Haiku 5.5면 건당 1원이 안 된다.
3. **이전 경로**: 나중에 AWS Bedrock으로 옮길 수 있다. (Bedrock ID `anthropic.claude-haiku-5-5`)

전환은 `.env`만 바꾸면 된다.

```env
AGENT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

> 확인일 2026-10-21. 출처:
> [모델 개요](https://platform.claude.com/docs/en/models/overview),
> [단가](https://platform.claude.com/docs/en/about-claude/pricing),
> [학습 데이터 사용 여부](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training),
> [Gemini 모델](https://ai.google.dev/gemini-api/docs/models),
> [Gemini 단가](https://ai.google.dev/gemini-api/docs/pricing).
> 모델과 단가는 바뀌므로, 바꿀 때 이 표와 확인일을 같이 고친다.

## ChatGPT 메모리에서 빌려 온 것과 바꾼 것

| 빌려 온 것 | 이 에이전트에서 |
| --- | --- |
| 기억 쓰기와 꺼내기를 분리 | STEP(쓰기)과 DAILY(꺼내기)를 따로 둔다 |
| 일이 생길 때 기억을 갱신 | 스텝 기록이 저장될 때 메모를 쓰고, 리포트 때 빠진 것만 따라잡는다 |
| 원본 대화와 따로 기억을 저장 | `agent_feedback`에 따로 저장한다 |

| 바꾼 것 | 왜 |
| --- | --- |
| 사실은 항상 원본에서 다시 계산 | 메모는 빠지거나 늦을 수 있다. 숫자를 메모에서 읽으면 틀린 칭찬이 나온다 |
| 무엇을 기억할지는 코드가 정함 | 모델이 고르면 무엇을 기억했는지 설명할 수 없다 |
| 건강 정보는 기억하지 않음 | 임산부 서비스라 민감정보다. 기억할 이유가 없다 |
| 메모는 하루·스텝 하나로 제한 | 길어질수록 리포트에 넣는 맥락이 흔들린다 |

## 팀 코드에서 가져온 값과 팀 확인 대기

컬럼 이름, `status`·`category` 값, 점수 범위, 목표 세트는 develop #15의 팀 모델·스키마·점수 규칙에 맞췄다. `config.py`
위쪽 블록에 출처와 함께 모아 두었고, 팀 코드가 바뀌면 그 블록만 고친다.

아직 팀 확인을 기다리는 것:

- `agent_feedback.exercise_step_records_id`의 NULL 허용 (DAILY 행은 비어야 한다. 팀 최종 ERD는 NOT NULL)
- 피드백 이벤트 코드 목록 (`rules/feedback_codes.json`은 CV 명세의 예시 6개)

읽지 않는 컬럼: `exercise_records.is_completed`(develop #15에서는 `status`가 `completed`일 때만 참이라
`status`와 같은 뜻이다. 완료 수는 `status` 하나로만 센다), `user_goal`(의미 미확정).
