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
- **Conda + pip 기반 패키지/실행 관리 (Ubuntu 기준)**

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
- Conda + pip (Dependencies)

---

## 🧪 가상환경 세팅 (Ubuntu + Conda 기준)

### 1) Conda 환경 생성/활성화
```bash
cd Gomguk-BE/backend
conda create -n gomguk-be python=3.11 -y
conda activate gomguk-be
```

### 2) 라이브러리 설치
```bash
pip install -r requirements.txt
```

---

## 🗄️ DB 연동 (Ubuntu + Docker Compose 기준)

### 1) `.env` 생성
`Gomguk-BE/.env.example`를 복사해서 `Gomguk-BE/.env`를 만들고 값들을 채워주세요.
```bash
cd Gomguk-BE
cp .env.example .env
```

### 2) (선택) Postgres 컨테이너만 실행
백엔드만 먼저 띄우고 싶으면 `db` 서비스만 올리면 됩니다.
```bash
docker compose up -d db
```

> `docker compose up -d`로 전체 스택(Airflow/MinIO 포함)을 올리려면,
> `proxy-net`이 external 네트워크라서 먼저 만들어야 합니다:
> ```bash
> docker network create proxy-net
> docker compose up -d
> ```

### 3) 스키마 생성 (처음 실행 기준, 실행 경로 주의)
```bash
cd Gomguk-BE/backend
alembic upgrade head
```

---

## ▶️ 서버 실행

### 1) 서버 실행
```bash
cd Gomguk-BE/backend
conda activate gomguk-be
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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

> 주의: 현재 설정은 필수 환경변수가 빠지면 앱 import 단계에서 바로 실패합니다.
> (`ACCESS_TOKEN_EXPIRE_MINUTES`, `DATABASE_URL`, `SECRET_KEY` 등)
