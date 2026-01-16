# Gomguk-BE Backend
> arXiv 논문 **추천 & 요약** 백엔드 시스템 (API + 크롤링/요약 파이프라인)  
> 현재는 **Google OAuth 로그인 + 기본 페이지 라우팅** 중심으로 구성 중이며, **GitHub OAuth는 추후 추가 예정**입니다.

![python](https://img.shields.io/badge/Python-3.10%2B-blue)
![framework](https://img.shields.io/badge/FastAPI-API-success)
![db](https://img.shields.io/badge/DB-PostgreSQL-blueviolet)
![auth](https://img.shields.io/badge/Auth-Google%20OAuth2-orange)

---

## ✨ 한 줄 소개
사용자 관심사/행동을 기반으로 논문을 수집하고, 선별·요약 후 **개인화 추천**으로 제공하는 백엔드입니다.

---

## ✅ 주요 기능 (WIP)
- **OAuth 로그인**
  - Google OAuth2 로그인/콜백 처리
  - 신규 유저 플로우(`is_new_user`) 지원
- **페이지/기능 라우팅**
  - 온보딩, 마이페이지, 검색 등 기본 엔드포인트 제공
- **DB 연동**
  - Docker 기반 PostgreSQL 로컬 개발 환경
  - 초기 테이블 생성 스크립트 제공

> 아래 문서는 “현재 레포 상태 기준”으로 로컬 실행/연동에 필요한 것만 정리했습니다.

---

## 🧭 서버 엔드포인트

- `/`
- `/oauth/google/login`  
  - 구글 로그인 페이지로 리디렉션
- `/oauth/google/callback`  
  - 로그인 후 구글 토큰 획득 → 사용자 정보 가져온 후 토큰 발급  
  - 새 유저면 `is_new_user = true` → 온보딩으로 리디렉션 필요
- `/mypage`
- `/onboarding`
- `/search`

---

## 🚀 빠른 시작 (Windows CMD 기준)

### 1) 가상환경 세팅
1) 가상환경 생성  
   `C:\Gomguk-BE\backend>uv venv .venv`

2) 인터프리터 설정 (PyCharm 기준)  
   - `File → Settings → Python → Interpreter`  
   - Python Interpreter를 아래 경로로 설정:  
     - `C:\Gomguk-BE\backend\.venv\Scripts\python.exe`

3) 라이브러리 설치  
   `C:\Gomguk-BE\backend>uv pip install -r requirements.txt`

---

## 🐘 DB 연동 (Docker + Postgres, Windows CMD 기준)

> ⚠️ **가상환경 세팅을 먼저 진행해 주세요!!**

1) DB 저장 폴더 생성  
   `C:\>mkdir C:\docker\pgdata`

2) 컨테이너 생성 및 실행

   - `C:\>docker run -d --name pg ^
   More?   -e POSTGRES_USER=postgres ^
   More?   -e POSTGRES_PASSWORD=<"기타 페이지를 참조해 pw를 입력해주세요!"> ^
   More?   -e POSTGRES_DB=app ^
   More?   -e TZ=Asia/Seoul ^
   More?   -p 5433:5432 ^
   More?   -v C:\docker\pgdata:/var/lib/postgresql/data ^
   More?   postgres:16-alpine`

3) 실행 확인 (1이 출력되어야 합니다)  
   - `C:\>docker ps`  
   - `C:\>docker exec -it pg psql -U postgres -d app -c "select 1;"`

4) 테이블 생성 (이미 있을 시 무시됩니다) *(실행 경로 주의)*  
   `C:\Gomguk-BE\backend>uv run python -m app.core.init_db_once`

5) 테이블 확인  
   `C:\>docker exec -it pg psql -U postgres -d app -c "\dt"`

---

## 🔧 환경 변수 (.env) 가이드 (권장)

`.env`는 **커밋하지 말고** 로컬에서만 관리하세요.

- 예시 키(프로젝트 상황에 맞게 채우기):
  - `DATABASE_URL` (Postgres)
  - `SECRET_KEY`
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI`

> 위 키 이름은 프로젝트 설정 코드에 따라 달라질 수 있습니다.  
> 실제 사용 중인 키 이름을 `app/core/config.py`의 Settings에서 확인하세요.

---

## 🧩 개발 팁

- **경로/모듈 에러가 나면**
  - 커맨드는 되도록 `C:\Gomguk-BE\backend`에서 실행
  - PyCharm Interpreter가 `.venv`로 잡혀있는지 확인
- **Postgres 포트**
  - `-p 5433:5432`이므로, 호스트에서는 **5433 포트**로 접속합니다.
