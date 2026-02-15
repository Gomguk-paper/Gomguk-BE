# Gomguk-BE

Gomguk 백엔드 서버(FastAPI) 프로젝트입니다.

## 문서

- API 명세서: `API-SPEC.md`
- 백엔드 코드: `backend/`
- Airflow/DAG: `dags/`

## 빠른 시작

### 1) 의존성 설치

```powershell
cd backend
uv sync
```

### 2) 인프라 실행

전체:

```powershell
cd ..
docker compose up -d
```

백엔드 로컬 확인 최소 구성(DB + MinIO):

```powershell
docker compose up -d db minio
```

### 3) 마이그레이션

```powershell
cd backend
uv run alembic upgrade head
```

### 4) 서버 실행

```powershell
uv run uvicorn app.main:app --reload
```

### 5) Swagger

- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`

## 운영 체크

- API root path: `/api`
- 이미지 공개 경로
  - paper: `http://gomguk.cloud/papers/...`
  - profile: `http://gomguk.cloud/profiles/...`
- Nginx/Ingress 프록시 필요
  - `/papers/` -> MinIO `papers` 버킷
  - `/profiles/` -> MinIO `profiles` 버킷

## 자주 쓰는 명령

```powershell
uv sync
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run uvicorn app.main:app --reload
```
