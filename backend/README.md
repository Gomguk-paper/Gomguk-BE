# Jaram Paper Backend
> arXiv 논문 **추천 & 요약** 백엔드 시스템 (API + 크롤링/요약 파이프라인)

![python](https://img.shields.io/badge/Python-3.10%2B-blue)
![framework](https://img.shields.io/badge/FastAPI-API-success)
![db](https://img.shields.io/badge/DB-SQLite-lightgrey)
![license](https://img.shields.io/badge/License-MIT-informational)

---

## ✨ 한 줄 소개
사용자 관심사/행동을 기반으로 arXiv 논문을 수집하고, 선별·요약 후 **개인화 추천**으로 제공하는 백엔드입니다.

## ✅ 주요 기능
- **추천 논문 조회 API**
  - 사용자 정보를 기반으로 추천 알고리즘을 통해 논문을 반환
- **논문 크롤링 및 요약 파이프라인**
  - 크롤링 → 선별 → 요약 자동화
- **검색/마이페이지 기능(연동 전제)**
  - 검색: 태그/필터
  - 마이페이지: 저장/좋아요/히스토리

---

## 📦 프로젝트 문서
- `SETUP_GUIDE.md` : 설치 및 실행 가이드
- `API_GUIDE.md` : API 사용 가이드
- `README_STRUCTURE.md` : 프로젝트 구조 설명

---

## 🚀 빠른 시작 (Quick Start)

```bash
cd backend
pip install -r requirements.txt

python -c "from core.database import init_db; init_db()"
python init_demo_data.py

python main.py
```

- 서버: http://localhost:8000
- Swagger 문서: http://localhost:8000/docs

---

## 🔧 환경 변수 설정
루트(혹은 `backend` 디렉토리)에 `.env` 파일을 만들고 아래를 추가하세요.

```env
DATABASE_URL=sqlite:///./data/papers.db
OPENAI_API_KEY=your_openai_api_key_here

API_HOST=0.0.0.0
API_PORT=8000

ARXIV_CATEGORIES=cs.AI,cs.LG,cs.CV,cs.CL
MAX_PAPERS_PER_CRAWL=100
TOP_CITATIONS_COUNT=5
```

> `OPENAI_API_KEY`가 없으면 **데모용 요약**이 생성됩니다.

---

## 🧭 엔드포인트
- `/` : 메인페이지 - 50개 배치 추천
- `/onboarding` : 온보딩
- `/search` : 검색 - 태그/필터 기능
- `/mypage` : 마이페이지 - 저장/좋아요/히스토리

> 주요 API 엔드포인트는 **(예정)** 입니다.

---

## 🧪 파이프라인 실행
크롤링-선별-요약 파이프라인을 수동 실행:

```bash
python pipeline.py
```

---

## 🧠 추천 알고리즘 개요
추천 점수는 아래 요소들을 종합해 계산합니다.

- **기본 점수**
  - 인용수, 트렌딩 점수, 최신성 점수
- **태그 매칭**
  - 사용자 관심 태그 ↔ 논문 태그 일치도
- **사용자 레벨 가중치**
  - 연구자: 인용수 비중↑
  - 실무자: 최신성 비중↑
- **사용자 행동 반영**
  - 좋아요/저장한 논문 점수 증가
- **제외/감점**
  - 이미 본 논문 점수 감소

---

## ⚠️ 주의사항 / 운영 팁
- 실제 인용수는 **Semantic Scholar API 등 외부 연동**이 필요합니다. (현재는 데모 데이터 기반)
- 프로덕션에서는 CORS를 `*`로 두지 말고 **허용 도메인 제한**을 권장합니다.

---

## 🤝 Contributing
이슈/PR 환영합니다.
- 기능 제안 → Issue
- 버그 수정/기능 추가 → PR

---

## 📄 License
프로젝트 라이선스는 레포의 `LICENSE` 파일을 따릅니다.
