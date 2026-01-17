# Gomguk-BE (Backend)

OAuth 기반 로그인(현재 Google, GitHub OAuth 추가 예정) + 온보딩/마이페이지/검색을 제공하는 FastAPI 백엔드입니다.

---

## ✨ 한 줄 소개
사용자 인증(OAuth) → 신규 유저 온보딩 → 마이페이지/검색 기능까지 이어지는 기본 흐름을 제공하는 백엔드 서버입니다.

---

## ✅ 주요 기능
- **Google OAuth 로그인**
  - 로그인 페이지 리디렉션
  - 콜백에서 Google 토큰 획득 → 사용자 정보 조회 → 서비스 토큰 발급
  - 신규 유저면 `is_new_user = true` → 온보딩 플로우로 이동 필요
- **온보딩 / 마이페이지**
- **검색 엔드포인트**
- **PostgreSQL + Alembic 마이그레이션**
- **uv 기반 패키지/실행 관리**

---

## 🌐 서버 엔드포인트
- `GET /`
- `GET /oauth/google/login`
  - 구글 로그인 페이지로 리디렉션
- `GET /oauth/google/callback`
  - 로그인 후 구글 토큰 get → 사용자 정보 가져온 후 토큰 발급
  - 새 유저면 `is_new_user = true` → 온보딩으로 리디렉션 필요
- `GET /mypage`
- `GET /onboarding`
- `GET /search`

> GitHub OAuth는 추후 추가 예정

---

## 🧰 개발 환경
- Python 3.10+
- FastAPI / Uvicorn
- PostgreSQL (Docker Compose)
- SQLModel / SQLAlchemy
- Alembic (Migration)
- uv (Dependencies)

---

## 🧪 가상환경 세팅 (cmd 기준)

### 1) 가상환경 생성
```powershell
C:\Gomguk-BE\backend> uv venv .venv
```

### 2) 인터프리터 설정 (Pycharm 기준)
```text
File → Settings → Python → Interpreter에서 Python Interpreter를
C:\Gomguk-BE\backend\.venv\Scripts\python.exe 로 설정해줍니다.
```

### 3) 라이브러리 설치
```powershell
C:\Gomguk-BE\backend> uv sync
```

---

## 🗄️ DB 연동법 (cmd 기준, 가상환경 세팅을 먼저 진행해 주세요!!)

### 1) .env 복붙 + DB 저장 폴더 생성
`.env`를 `Gomguk-BE/`에 복붙하고, DB 저장용 폴더를 만들어줍니다.
```powershell
C:\> mkdir C:\docker\pgdata
```

### 2) 컨테이너 생성 및 실행
```powershell
C:\> cd C:\Gomguk-BE
C:\Gomguk-BE> docker compose up -d
```

### 3) 스키마 생성 (처음 실행 기준, 실행 경로 주의)
```powershell
C:\> cd C:\Gomguk-BE\backend
C:\Gomguk-BE\backend> alembic upgrade head
```

---

## ▶️ 서버 실행

### 1) 가상환경 활성화
```powershell
C:\> cd C:\Gomguk-BE\backend\.venv\Scripts
C:\Gomguk-BE\backend\.venv\Scripts> activate
(.venv) C:\Gomguk-BE\backend\.venv\Scripts>
```

### 2) 서버 실행
```powershell
(.venv) C:\> cd C:\Gomguk-BE\backend
(.venv) C:\Gomguk-BE\backend> uv run uvicorn app.main:app --reload
```

---

## 📦 패키지 관련 (uv)
- uv를 사용하고, `pyproject.toml`로 의존성을 관리합니다.
- `uv.lock`은 상세 버전까지 자동 고정하는 파일입니다.

```powershell
uv sync                         # 패키지 동기화
uv add "패키지이름[추가기능]"    # 패키지 설치
```

---

## 🧱 DB 관련 (Alembic)
- Alembic은 SQLAlchemy/SQLModel 기반 프로젝트에서 스키마 변경을 마이그레이션으로 관리하는 도구입니다.
- 이 프로젝트에서는 `models.py`에 정의된 모델 중 `SQLModel`을 상속하고 `table=True`인 클래스를 테이블로 인식하며,
  Alembic이 이를 기준으로 변경 사항을 추적합니다.

```powershell
alembic revision --autogenerate -m "init"
# 현재 DB 상태와 models.py(SQLModel.metadata)를 비교해
# 변경사항을 app/alembic/versions/*.py 마이그레이션 파일로 생성합니다.

alembic upgrade head
# 최신 revision(head)까지 실제 DB에 적용합니다. (online)

alembic downgrade -1
# 가장 최근에 적용한 마이그레이션 1개를 되돌립니다. (권장)

alembic upgrade head --sql
# offline 모드: DB에 적용하지 않고 실행될 SQL만 출력합니다.
# (배포 전 SQL 검토/테스트용)
```

---

## 🔐 환경변수(.env) (권장)
- 실제 시크릿/키는 공유하지 말고, 필요하면 `.env.example`로 템플릿만 공유하세요.
- 보통 아래 값들이 필요합니다:
  - DB 접속 정보
  - OAuth Client ID / Client Secret
  - 서버 `SECRET_KEY`, 토큰 만료시간 등
