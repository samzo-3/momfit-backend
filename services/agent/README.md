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
| `models/agent/` | `agent_step_feedback.py`, `agent_daily_feedback.py`, `daily_feedback_source.py` | 팀 최종 ERD의 에이전트 테이블 셋 (에이전트의 쓰기 대상은 이 셋뿐) |
| `repositories/agent/` | `agent_feedback_repository.py` | STEP 메모·DAILY 저장과 조회, DAILY가 참고한 메모 잇기 |
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
`agent_step_feedback.exercise_step_records_id`는 팀의 `exercise_step_records`를 FK로 가리키므로,
`models/agent/agent_step_feedback.py`가 팀 모델 3개(`exercise`, `exercise_step`, `exercise_step_record`)를
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

### 저장한 리포트 다시 쓰기

LLM은 오늘 리포트에만 부르고, 그것도 그날 마지막 리포트 뒤에 기록이 바뀌었을 때만 부른다.
그날 마지막으로 저장한 DAILY를 그대로 쓸 수 있으면 LLM 없이 돌려주고 새로 저장하지 않는다.
숫자는 언제나 팀 테이블에서 다시 센다.

저장한 DAILY를 그대로 쓰려면 둘 다 맞아야 한다.

- 그날 기록이 마지막으로 바뀐 뒤에 숫자를 셌다. 팀 기록의 `modified_at`과 DAILY의 `created_at`을
  비교한다. `created_at`은 저장 시각이 아니라 숫자를 센 시각이다.
- 대체 문장이 아니다. 대체 문장은 '잠시 후 다시 확인해 주세요'라고 했으니 오늘은 다시 만든다.

쓸 수 없을 때 오늘은 새로 만든다. 지난 날짜는 다시 만들지 않고 숫자만으로 쓴 문장
(`이날 운동 3회, … 하신 기록이 있어요.`)을 돌려준다.

### 저장 테이블 (팀 최종 ERD)

| 테이블 | 무엇을 | 쌓는 방식 |
| --- | --- | --- |
| `agent_step_feedback` | STEP 메모. `exercise_step_records_id`에 그날 그 스텝의 마지막 시도 번호를 넣는다 | 다시 쓰면 새 행, 같은 스텝의 가장 최근 행이 현재 메모 |
| `agent_daily_feedback` | DAILY 한마디 + 다음 집중 스텝 한 줄(`today_summary`), 날짜(`report_date`, KST 자정) | 다시 만들면 새 행, 그날 가장 최근 행이 그날 리포트 |
| `daily_feedback_sources` | DAILY 한 행이 참고한 STEP 메모들 | DAILY를 저장할 때 함께 |

- STEP 메모 테이블에는 날짜 컬럼이 없다. 그날 메모는 그날 팀 스텝 기록 번호로 찾는다.
- `daily_feedback_sources`에는 LLM이 쓴 한마디만 잇는다. 대체 문장은 숫자만으로 썼으니 잇지 않는다.
- `today_summary`는 ERD상 `VARCHAR(255)`다. 한마디와 다음 집중 스텝 줄을 합쳐 255자를 넘으면 출력 검사
  실패로 보고 대체 문장을 쓴다. (저장하지 않는 fixture 모드도 똑같이 걸러서 두 모드가 같은 문장을 보여 준다)
- FK는 모두 `ON DELETE CASCADE`다. ERD가 정하지 않은 부분이라 사용자 승인을 받고 뒀다. 팀의 탈퇴 삭제나
  스텝 기록 삭제가 에이전트 테이블 때문에 막히지 않고, 지울 때 에이전트 행도 함께 지워진다.
- 컬럼 이름·타입·NULL 여부·FK는 `tests/agent/test_agent_erd_tables.py`가 ERD와 대조한다.
- `create_all`은 이미 있는 테이블을 고치거나 지우지 않는다. 예전 `agent_feedback` 테이블이 있는 DB에는 그
  테이블이 그대로 남고(에이전트는 더 쓰지 않는다), 새 테이블 셋은 서버를 띄울 때 만들어진다.

fixture 모드는 저장한 리포트가 없으니 이 규칙 없이 요청마다 새로 만든다.

## 경계

- fixture 모드(가짜 기록)는 에이전트 테이블을 읽지도 쓰지도 않는다. 가짜 기록으로 만든 메모·리포트가
  실제 사용자 계정에 쌓이지 않게 하고, STEP 메모의 FK가 DB에 없는 가짜 기록 번호를 가리켜 MySQL이
  거부하는 일을 막는다. 그래서 fixture 모드에서는 요청마다 STEP 메모를 새로 만든다.
- 팀 테이블은 읽기만 한다. 쓰기는 에이전트 테이블 셋뿐이다. 읽는 팀 테이블은 `exercises`,
  `exercise_steps`, `exercise_records`, `exercise_step_records`, `voice_cues`다.
- 일반 운동 점수(`exercise_records.total_score`)는 자세 점수가 아니라 '완료 세트 × 세트당 점수'다.
  리포트는 '완료 세트 / 목표 세트'로 보여 준다. 완료 세트는 `exercise_records.completed_sets`,
  목표 세트는 팀 점수 규칙(`services/pose_coaching/exercise_scoring_config.py`)에서 읽는다. LLM에는 일반 운동
  점수를 자세 평가처럼 말하지 말라고 한다. (`prompts/daily_system.md`)
- 스텝 통과 횟수는 `exercise_step_records.step_result_status`(PASS, 80점 이상)로 센다. STEP 메모에 LLM을
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

**개발과 운영 모두 Claude API (`claude-haiku-5-5`)**

처음에는 개발을 Gemini 무료 등급으로 하고, 실제 사용자 데이터가 들어가기 전에 Claude로 바꿀 계획이었다.
2026-10-21~22에 둘을 가짜 기록 시나리오(`run_scenarios`)로 돌려 보고 개발도 Claude로 바꿨다.

| 항목 | Gemini 무료 등급 (2026-10-21) | Claude Haiku 5.5 (2026-10-22) |
| --- | --- | --- |
| 모델 / 프롬프트 | `gemini-3.8-flash`·`gemini-3.5-flash` / daily-v2 | `claude-haiku-5-5` / daily-v3 |
| LLM을 부르는 시나리오 4개 중 정상 | 실행 3번에서 0개, 2개, 3개 (나머지는 시간 초과·오류로 대체 문장) | 4개 모두 |
| 응답 시간 | 호출 하나에 11~15초 (호출 제한 10초를 자주 넘김) | 리포트 하나(호출 1~2번)에 3.4~8.3초 |
| 호출 한도 | 모델마다 하루 20번 | 분당 한도 안에서 충전한 크레딧만큼 |
| 리포트 한 건 비용 | 무료 | $0.00055~0.0012 (약 1원) |

문장 품질은 프롬프트 버전이 달라 두 모델을 직접 비교하지 않았다. daily-v3로 돌린 Claude 결과는
숫자가 모두 맞았고, 2~3문장·해요체·인용 규칙을 지켰다.

| 항목 | 값 |
| --- | --- |
| 모델 ID | `claude-haiku-5-5` |
| 입력 / 출력 (프롬프트 10만 토큰 이하) | $0.10 / $0.50 per MTok |
| 입력 / 출력 (프롬프트 10만 토큰 초과) | $0.50 / $2.50 per MTok |
| 캐시 히트 (10만 토큰 이하) | $0.01 per MTok |
| 컨텍스트 / 최대 출력 | 1M / 128K 토큰 |

Claude를 쓰는 이유는 네 가지다.

1. **속도와 안정성**: 리포트 전체 제한 시간(25초) 안에 여유 있게 끝난다. Gemini는 시간 초과로 대체 문장이 자주 나왔다.
2. **데이터**: 상용 API로 보낸 입력·출력은 별도 합의가 없으면 모델 학습에 쓰지 않는다. Gemini 무료 등급은
   입력·출력이 구글 제품 개선에 쓰일 수 있다. (유료 등급은 제품 개선에 쓰지 않는다고 적혀 있다.)
3. **단가**: 실측으로 리포트 한 건은 입력 약 2,400~4,100 토큰, 출력 약 470~1,650 토큰(생각 토큰 포함)이다.
   Haiku 5.5면 건당 1원 안팎이다. 출력 토큰은 생각한 양에 따라 시나리오마다 차이가 크다.
4. **이전 경로**: 나중에 AWS Bedrock으로 옮길 수 있다. (Bedrock ID `anthropic.claude-haiku-5-5`)

Gemini 제공자는 남겨 둔다. 키를 결제 없이 받아 무료로 비교해 볼 때 쓰고, 이때도 가짜 데이터만 넣는다.
운영(`AGENT_APP_ENV=prod`)에서는 `AGENT_PROD_PROVIDERS`(기본 `anthropic`)에 없어서 쓸 수 없다.

Claude로 돌리려면 환경변수 두 개를 바꾼다. (`compose.yaml`은 `.env`에서 읽는다)

```env
AGENT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

> 단가 확인일 2026-10-21, 실측 2026-10-21~22. 출처:
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
| 원본 대화와 따로 기억을 저장 | 에이전트 테이블(`agent_step_feedback`, `agent_daily_feedback`)에 따로 저장한다 |

| 바꾼 것 | 왜 |
| --- | --- |
| 사실은 항상 원본에서 다시 계산 | 메모는 빠지거나 늦을 수 있다. 숫자를 메모에서 읽으면 틀린 칭찬이 나온다 |
| 무엇을 기억할지는 코드가 정함 | 모델이 고르면 무엇을 기억했는지 설명할 수 없다 |
| 건강 정보는 기억하지 않음 | 임산부 서비스라 민감정보다. 기억할 이유가 없다 |
| 메모는 하루·스텝 하나로 제한 | 길어질수록 리포트에 넣는 맥락이 흔들린다 |

## 팀 코드에서 가져온 값과 팀 확인 대기

컬럼 이름, `status`·`category` 값, 점수 범위, 목표 세트는 develop #15의 팀 모델·스키마·점수 규칙에 맞췄다.
스텝 판정 컬럼은 develop 73d26a9에서 `status`에서 `step_result_status`로 옮겨졌다. `config.py`
위쪽 블록에 출처와 함께 모아 두었고, 팀 코드가 바뀌면 그 블록만 고친다.

`step_report`는 FE 자세 배우기 화면(momfit-frontend #13의 `saveSideKickStep.ts`)이 만든다. FE는 CV 명세와
이름이 다른 값을 쓴다. 판정은 `NON_PASS`(명세는 `FAIL`), 추적 상태는 `TRACKING_OK`(명세는 `VALID`)다.
그래서 읽는 경계(`team_activity_reader.py`)에서 명세 이름으로 바꾼다. FE는 음성 안내를 할 때마다 피드백 코드를
쌓아 한 시도에 같은 코드가 여러 번 들어 있으므로, 시도 하나에서는 한 번만 센다. FE는 점수가 한 번이라도
매겨진 스텝만 저장해서, 측정 불가(카메라 위치 안내) 시도는 지금 FE에서 오지 않는다.

아직 팀 확인을 기다리는 것:

- 피드백 이벤트 코드 목록 (`rules/feedback_codes.json`은 FE #13 채점 코드 13개와 CV 명세의
  `TRACKING_UNAVAILABLE`이다. 팀 공통 목록이 따로 정해지면 맞춘다)
- 교정 문장으로 쓰는 `voice_cues` 행 (FE는 음성 목록 파일을 직접 읽고 DB `voice_cues`는 비어 있다.
  행이 없으면 리포트는 교정 문장 없이 상태 설명만 쓴다)

읽지 않는 컬럼: `exercise_records.is_completed`(develop #15에서는 `status`가 `completed`일 때만 참이라
`status`와 같은 뜻이다. 완료 수는 `status` 하나로만 센다), `user_goal`(의미 미확정).
