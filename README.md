# MomFit Backend

MomFit 백엔드는 **FastAPI**를 기반으로 사용자 및 인증 정보, 운동 관련 비즈니스 로직을 관리하는 프로젝트입니다.

---

## 1. 프로젝트 구조

### 1.1. 전체 디렉터리 구조

`api/`, `services/`, `models/` 등은 프로젝트 **루트에 분리**하여 배치합니다. 별도의 `app/` 상위 디렉터리는 사용하지 않습니다.

```text
momfit-backend/
├── api/
│   ├── __init__.py
│   ├── auth.py
│   ├── deps.py
│   ├── health.py
│   ├── kakao_auth.py
│   └── users.py
├── core/
│   ├── __init__.py
│   ├── clock.py
│   ├── config.py
│   ├── errors.py
│   └── security.py
├── db/
│   ├── __init__.py
│   ├── base.py
│   └── session.py
├── docs/
│   └── troubleshooting.md
├── media/
│   └── videos/
│       └── exercises/
│           ├── shoulder-stretch/
│           │   └── .gitkeep                
│           ├── side-step-open-window/
│           │   └── .gitkeep               
│           └── squat/
│               └── .gitkeep                
├── models/
│   ├── __init__.py
│   ├── auth_identity.py
│   ├── email_verification.py
│   ├── refresh_token.py
│   └── user.py
├── repositories/
│   ├── __init__.py
│   ├── auth_identity_repository.py
│   ├── email_verification_repository.py
│   ├── refresh_token_repository.py
│   └── user_repository.py
├── schemas/
│   ├── __init__.py
│   ├── auth.py
│   ├── email_verification.py
│   ├── user.py
│   └── validators.py
├── scripts/                                # 수동·cron 실행용 스크립트
│   └── purge_withdrawn.py                  # 유예 기간이 지난 탈퇴 계정 삭제
├── services/ # 기능별로 디렉토리 구분
│   ├── __init__.py
│   ├── auth/                               # 인증·인가
│   │   ├── __init__.py
│   │   ├── account_service.py              # 회원 탈퇴(30일 유예), 복구, 만료 계정 삭제
│   │   ├── auth_service.py
│   │   ├── email_verification_service.py
│   │   ├── kakao_auth_service.py
│   │   ├── kakao_client.py
│   │   └── mailer.py
│   ├── user/                               # 사용자 프로필
│   │   ├── __init__.py
│   │   ├── pregnancy.py
│   │   └── user_service.py
│   └── pose_coaching/                      # 자세 배우기 모드     
│       ├── __init__.py                 
│       ├── side_step_open_window/
│       │   └── placeholder.py                                    
│       └── common/
│           └── placeholder.py             
├── tests/
│   ├── pose_coaching/                      
│   │   └── placeholder.py               
│   ├── conftest.py
│   ├── helpers.py
│   └── test_*.py                           
├── .dockerignore
├── .env.example
├── .gitignore
├── compose.local.yaml
├── compose.yaml
├── Dockerfile
├── main.py
├── pytest.ini
├── README.md
├── requirements-dev.txt
├── requirements.txt
└── TECH_STACK.md
```

> **로컬 전용 파일:** `.env`, `.venv/`, `__pycache__/`, `.idea/` 등은 위 버전 관리 대상 트리에서 제외합니다. 실제 Git 추적 여부는 `.gitignore` 및 `git status`로 확인합니다. `test_*.py`는 개별 파일명이 아니라 테스트 파일명 패턴입니다.
>
> **구현 상태:** `placeholder.py`와 `.gitkeep`은 디렉터리를 팀원과 공유하기 위한 임시 파일입니다. 자세 코칭 분석, 운동 영상 업로드, 영상 URL 제공 API 및 스토리지 연동이 완료되었다는 의미가 아닙니다.

### 1.2. 디렉터리별 역할

| 경로 | 역할 및 관리 대상 |
| --- | --- |
| `api/` | FastAPI Router 및 HTTP 요청·응답 처리. 인증, 카카오 인증, 사용자, 헬스체크 라우터와 의존성 주입 관련 파일을 포함합니다. |
| `core/` | 환경변수와 애플리케이션 공통 설정, 보안, 오류 처리, 시간 관련 유틸리티를 관리합니다. |
| `db/` | SQLAlchemy Base, 데이터베이스 연결 및 Session 구성을 관리합니다. |
| `docs/` | 프로젝트 운영 및 장애 해결 문서를 관리합니다. 현재 목록에 `troubleshooting.md`가 있습니다. |
| `models/` | SQLAlchemy ORM 모델. 사용자, 인증 식별자, 리프레시 토큰, 이메일 인증 모델 파일을 포함합니다. |
| `schemas/` | Pydantic 기반 요청·응답 데이터 검증과 직렬화. 인증·사용자·이메일 인증 Schema 및 검증 함수 파일을 포함합니다. |
| `repositories/` | 데이터베이스 접근 및 CRUD 계층. 사용자, 인증 식별자, 리프레시 토큰, 이메일 인증 데이터의 조회·저장 등을 담당합니다. |
| `services/` | 비즈니스 로직. 기능별 하위 디렉터리로 나눕니다. 향후 MediaPipe·YOLO 관련 처리도 이 계층에서 역할에 맞게 분리할 수 있습니다. |
| `services/auth/` | 인증·인가. 가입·로그인·토큰, 이메일 인증, 메일 발송, 카카오 로그인·클라이언트, 회원 탈퇴(30일 유예)·복구·만료 계정 삭제를 담당합니다. |
| `services/user/` | 사용자 프로필 조회·수정, 온보딩, 임신 주차 계산을 담당합니다. |
| `scripts/` | 서버 밖에서 수동이나 cron으로 실행하는 스크립트. 현재는 유예 기간이 지난 탈퇴 계정을 삭제하는 `purge_withdrawn.py`가 있습니다. |
| `services/pose_coaching/` | **구현 예정:** 운동 자세 분석·코칭을 위한 상위 모듈입니다. 현재는 디렉터리와 임시 파일만 준비되어 있습니다. |
| `services/pose_coaching/common/` | **구현 예정:** 여러 운동에서 재사용할 공통 데이터 구조, 특징값 계산 및 공통 계산을 관리합니다. |
| `services/pose_coaching/analyzers/` | **구현 예정:** 사이드 스텝, 스쿼트 등 운동별 자세 분석 모듈을 관리합니다. |
| `services/pose_coaching/tracking/` | **구현 예정:** 사람·사용자 및 관절 추적 관련 처리를 관리합니다. |
| `services/pose_coaching/references/` | **구현 예정:** 운동별 기준 자세 및 평가 참고 데이터를 관리합니다. |
| `media/videos/exercises/` | **구현 예정:** 운동별 동영상 저장 디렉터리입니다. 현재는 `.gitkeep`으로 폴더만 유지합니다. |
| `tests/` | 테스트 코드 및 공통 테스트 설정. 인증, 사용자, 이메일 검증, 헬스체크 등 기능을 검증하기 위한 테스트 파일과 도우미를 관리합니다. |
| `tests/pose_coaching/` | **구현 예정:** 자세 코칭 기능을 검증할 테스트를 관리합니다. |

### 1.3. 주요 파일 역할

| 파일 | 역할 |
| --- | --- |
| `main.py` | FastAPI 애플리케이션 진입점입니다. |
| `Dockerfile` | 백엔드 Docker 이미지 빌드 설정입니다. |
| `compose.yaml` | Backend 및 MySQL 등의 컨테이너 구성을 위한 Compose 파일입니다. 구체적인 실행 서비스는 실제 파일을 기준으로 확인합니다. |
| `compose.local.yaml` | 로컬 개발 환경을 위한 별도 Compose 설정 파일입니다. |
| `.dockerignore` | Docker 이미지 빌드에 포함하지 않을 파일을 지정합니다. |
| `.gitignore` | Git이 추적하지 않을 파일과 디렉터리를 정의합니다. |
| `.env.example` | 팀원에게 공유할 개발 환경변수 예시입니다. 실제 비밀값을 넣는 `.env`와 구분합니다. |
| `requirements.txt` | 백엔드 실행에 필요한 Python 패키지 의존성을 관리합니다. |
| `requirements-dev.txt` | 개발 및 테스트용 Python 패키지 의존성을 관리합니다. |
| `pytest.ini` | pytest 설정 파일입니다. |
| `TECH_STACK.md` | 팀 공통 기술 스택 및 버전 관리 문서입니다. |
| `README.md` | 프로젝트 구조, 파일별 책임, 영상 관리 방향 및 협업 규칙을 설명합니다. |

### 1.4. 백엔드 계층 구조

일반적인 데이터 처리 흐름은 다음과 같습니다.

```text
Client (React)
      │ HTTP 요청
      ▼
Router (api/)
      │ 요청 전달
      ▼
Service (services/)
      │ 데이터 접근이 필요할 때
      ▼
Repository (repositories/)
      │ SQLAlchemy
      ▼
Database (MySQL)
```

| 계층 | 역할 |
| --- | --- |
| **Router** | HTTP 요청을 받아 적절한 Service로 전달하고 응답을 반환합니다. |
| **Service** | 비즈니스 규칙, 유효성 확인 및 데이터 처리를 담당합니다. |
| **Repository** | 데이터베이스 조회·저장·수정·삭제(CRUD)를 담당합니다. |
| **Database** | MySQL에 영속 데이터를 저장합니다. |

**참고:** AI 추론 등 데이터베이스 접근이 필요 없는 서비스는 Repository 계층을 반드시 거칠 필요가 없습니다. `schemas/`는 요청·응답 검증, `models/`는 데이터베이스 구조를 표현하는 역할로 위 흐름에 함께 참여할 수 있습니다.

### 1.5. 자세 코칭 모듈 설계 방향

| 모듈 | 계획된 책임 |
| --- | --- |
| `common/` | 운동 종류와 무관하게 사용할 데이터 구조와 공통 특징값·각도 계산 |
| `analyzers/` | 운동별 자세 판정 및 분석 로직 |
| `tracking/` | 사람 및 관절의 추적 결과 처리 |
| `references/` | 운동별 기준 자세와 판정 참고 데이터 |
| `tests/pose_coaching/` | 자세 코칭 동작과 경계 조건 검증 |

이처럼 역할을 분리하면 **운동 종류가 늘어나더라도 공통 계산과 추적 로직을 중복 구현하지 않아도 됩니다.** 또한 운동별 분석 기준 변경과 테스트 범위를 구분해 여러 개발자가 협업하기 쉽습니다.

현재 `pose_coaching/` 하위의 `placeholder.py` 및 `references/.gitkeep`은 **구조 공유용**입니다. 실제 분석 파일과 기능은 이후 개발 단계에서 추가합니다.

### 1.6. 운동 영상 관리 규칙

- 영상은 **운동별 slug**를 기준으로 디렉터리를 나눕니다. 예: `media/videos/exercises/side-step-open-window/`
- 영상 파일명은 용도와 버전을 드러내도록 작성합니다. 예: `learn-v1.mp4`(자세 배우기), `guide-v1.mp4`(운동 가이드)
- 향후 FastAPI와 MySQL에서 운동 영상의 **메타데이터 및 저장 경로**를 관리할 계획입니다. MySQL에 MP4 파일 자체를 저장하는 구조를 뜻하지는 않습니다.
- 프론트엔드는 백엔드로부터 받은 영상 URL을 사용해 영상을 재생하도록 설계할 수 있습니다.
-

예정 파일 구조 예시는 다음과 같습니다.

```text
media/videos/exercises/
├── side-step-open-window/
│   ├── learn-v1.mp4
│   └── guide-v1.mp4
├── squat/
│   └── learn-v1.mp4
└── shoulder-stretch/
    └── learn-v1.mp4
```

---

## 2. Commit Convention

### 2.1. 커밋 메시지 형식

```text
<작업 타입>: <작업 내용>
```

**작성 예시**

```text
feat: 회원가입 API 구현
fix: 로그인 토큰 만료 오류 수정
docs: README 프로젝트 구조 수정
```

### 2.2. 작업 타입

| 타입 | 사용 목적 | 커밋 메시지 예시 |
| --- | --- | --- |
| `begin` | 프로젝트 초기 설정 | `begin: MomFit 백엔드 초기 구조 생성` |
| `feat` | 새로운 기능 추가 및 구현 | `feat: 회원가입 API 구현` |
| `docs` | 문서 추가 및 수정 | `docs: API 명세서 업데이트` |
| `add` | 기존 기능에 코드 추가 및 수정 | `add: 회원 조회 로직에 페이징 추가` |
| `typos` | 단순 오타 수정 | `typos: 변수명 오타 수정` |
| `fix` | 버그 및 에러 수정 | `fix: 중복 운동 기록 저장 오류 수정` |
| `test` | 테스트 코드 작성 및 수정 | `test: 회원가입 서비스 테스트 코드 작성` |
| `rename` | 파일·폴더 이름 및 경로 변경 | `rename: 사용자 Schema 파일명 변경` |
| `refactor` | 기능 변경 없는 코드 구조 개선 | `refactor: 사용자 서비스 로직 분리` |
| `comment` | 주석 추가 및 수정 | `comment: 자세 분석 함수 설명 추가` |
| `remove` | 파일 및 코드 삭제 | `remove: 사용하지 않는 유틸리티 삭제` |
| `branch` | 브랜치 추가 및 병합 관련 작업 | `branch: develop 브랜치 병합` |
| `chore` | 환경 설정·빌드·의존성 관리 | `chore: Docker 설정 변경` |

### 2.3. 커밋 작성 규칙

1. 위 표에 정의된 작업 타입을 사용합니다.
2. 작업 내용은 변경 사항을 명확하게 설명합니다.
3. 하나의 커밋에는 가급적 하나의 목적만 포함합니다.
4. 불필요한 수식어 없이 간결하게 작성합니다.
5. 단순 오타는 `typos`, 버그 수정은 `fix`를 사용합니다.
6. 새로운 기능은 `feat`, 기존 기능 확장은 `add`를 사용합니다.
7. 문서만 변경했다면 `docs`를 사용합니다.
8. 동작을 변경하지 않는 코드 구조 개선은 `refactor`를 사용합니다.

---

## 3. Branch Convention

### 3.1. 브랜치 구조

| 브랜치 | 역할 |
| --- | --- |
| `main` | 배포 가능한 안정 버전 관리 |
| `develop` | 개발 중인 기능을 통합하는 브랜치 |
| `feature/기능명` | 개별 기능을 개발하는 브랜치 |

### 3.2. 브랜치 생성 규칙

1. 기본 브랜치는 `main`, `develop`을 사용합니다.
2. 새로운 기능은 `develop`에서 `feature/기능명` 브랜치를 생성합니다.
3. 브랜치명은 소문자 영문을 사용합니다.
4. 여러 단어는 하이픈(`-`)으로 구분합니다.
5. 기능의 목적을 명확하게 표현합니다.
6. 작업 완료 후 `develop`을 대상으로 Pull Request(PR)를 생성합니다.

### 3.3. 브랜치명 예시

| 작업 목적 | 브랜치명 |
| --- | --- |
| 회원가입 | `feature/signup` |
| 로그인 | `feature/login` |
| AI 에이전트 | `feature/ai-agent` |
| 운동 자세 분석 | `feature/pose-analysis` |
| 운동 기록 관리 | `feature/exercise-history` |
| 객체 탐지 | `feature/object-detection` |

---

## 4. Pull Request Convention

### 4.1. PR 생성 규칙

1. 기능 개발 완료 후 `develop`을 대상으로 PR을 생성합니다.
2. PR 제목은 커밋 메시지와 동일한 형식을 사용합니다.
3. PR 본문에는 작업 내용, 주요 변경 사항 및 테스트 결과를 작성합니다.
4. **최소 1명 이상의 리뷰 승인**을 받습니다.
5. 필요한 테스트 및 코드 리뷰를 완료한 후 병합합니다.
6. 병합이 완료된 기능 브랜치는 삭제합니다.

### 4.2. PR 제목 형식

```text
<작업 타입>: <작업 내용>
```

**작성 예시**

```text
feat: 회원가입 API 구현
fix: 로그인 토큰 만료 오류 수정
refactor: 사용자 서비스 구조 개선
docs: API 명세서 업데이트
```

---

## 5. 작업 완료 체크리스트

### 5.1. Commit

- [ ] 정의된 작업 타입을 사용했는가?
- [ ] 커밋 메시지가 변경 내용을 명확히 설명하는가?
- [ ] 서로 무관한 작업이 한 커밋에 섞이지 않았는가?

### 5.2. Branch

- [ ] `develop`에서 기능 브랜치를 생성했는가?
- [ ] `feature/기능명` 형식을 따르는가?
- [ ] 소문자 및 하이픈 규칙을 지켰는가?
- [ ] 보호된 브랜치에 직접 Push하지 않았는가?

### 5.3. Pull Request

- [ ] 올바른 대상 브랜치로 PR을 생성했는가?
- [ ] PR 제목과 본문을 작성했는가?
- [ ] 테스트 결과를 작성했는가?
- [ ] 최소 1명의 리뷰 승인을 받았는가?
- [ ] 병합 후 기능 브랜치를 삭제했는가?
