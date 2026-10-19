# MomFit Backend

## 1. 프로젝트 구조

```text
.
├── api/
│   ├── __init__.py
│   └── health.py
├── core/
│   ├── __init__.py
│   └── config.py
├── db/
│   ├── __init__.py
│   └── session.py
├── models/
│   └── __init__.py
├── schemas/
│   └── __init__.py
├── repositories/
│   └── __init__.py
├── services/
│   └── __init__.py
├── tests/
├── main.py
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
├── requirements.txt
├── TECH_STACK.md
└── README.md
```

### 1.1. 폴더별 역할

| 폴더 | 역할 |
|---|---|
| `api/` | FastAPI Router 및 HTTP 요청·응답 처리 |
| `core/` | 환경변수 및 애플리케이션 공통 설정 |
| `db/` | SQLAlchemy 연결 및 Session 관리 |
| `models/` | SQLAlchemy ORM 모델 정의 |
| `schemas/` | Pydantic 요청·응답 Schema 정의 |
| `repositories/` | 데이터베이스 접근 및 CRUD 로직 |
| `services/` | 비즈니스 로직 및 MediaPipe·YOLO 분석 |
| `tests/` | 테스트 코드 관리 |

### 1.2. 주요 파일 역할

| 파일 | 역할 |
|---|---|
| `main.py` | FastAPI 애플리케이션 진입점 |
| `Dockerfile` | 백엔드 Docker 이미지 빌드 설정 |
| `compose.yaml` | Backend 및 MySQL 컨테이너 구성 |
| `.dockerignore` | Docker 빌드에서 제외할 파일 정의 |
| `.gitignore` | Git에서 추적하지 않을 파일 정의 |
| `.env.example` | 개발 환경변수 예시 |
| `requirements.txt` | Python 실행 의존성 관리 |
| `TECH_STACK.md` | 팀 공통 기술 스택 및 버전 관리 |
| `README.md` | 프로젝트 구조 및 협업 규칙 문서 |

### 1.3. 백엔드 계층 구조

기본적인 데이터 처리 흐름은 다음과 같습니다.

`Router → Service → Repository → Database`

- **Router:** HTTP 요청을 받아 적절한 Service로 전달
- **Service:** 비즈니스 로직 및 데이터 처리
- **Repository:** 데이터베이스 조회·저장·수정·삭제
- **Database:** MySQL 데이터 저장

단, AI 추론 등 데이터베이스 접근이 필요 없는 서비스는 Repository 계층을 거치지 않을 수 있습니다.

---

## 2. Commit Convention

### 2.1. 커밋 메시지 형식

`<작업 타입>: <작업 내용>`

**작성 예시**

```text
feat: 회원가입 API 구현
fix: 로그인 토큰 만료 오류 수정
docs: README 프로젝트 구조 수정
```

### 2.2. 작업 타입

| 타입 | 사용 목적 | 커밋 메시지 예시 |
|---|---|---|
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
|---|---|
| `main` | 배포 가능한 안정 버전 관리 |
| `develop` | 개발 중인 기능을 통합하는 브랜치 |
| `feature/기능명` | 개별 기능을 개발하는 브랜치 |

### 3.2. 브랜치 생성 규칙

1. 기본 브랜치는 `main`, `develop`을 사용합니다.
2. 새로운 기능은 `develop`에서 `feature/기능명` 브랜치를 생성합니다.
3. 브랜치명은 소문자 영문을 사용합니다.
4. 여러 단어는 하이픈(`-`)으로 구분합니다.
5. 기능의 목적을 명확하게 표현합니다.
6. 작업 완료 후 `develop`을 대상으로 PR을 생성합니다.

### 3.3. 브랜치명 예시

| 작업 목적 | 브랜치명 |
|---|---|
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

`<작업 타입>: <작업 내용>`

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