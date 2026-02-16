# Gomguk API Spec

이 문서는 프런트엔드 연동용 API 명세서입니다.  
기준 코드: `backend/app/api/routes/*`

## Base

- Base URL: `https://<host>/api`
- 로컬 예시: `http://localhost:8000/api`
- 인증: Cookie 우선 (`access_token`, `refresh_token`)
- 보조 인증: `Authorization: Bearer <token>`

인증 실패 공통 응답:

```json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "Login required."
  }
}
```

## Enums

- `source`: `arxiv` | `github`
- `sort` (`GET /paper`): `popular` | `recent`
- `summary style`: `plain` | `detailed` | `dc` | `basic_aggro` | `instagram_card_news`

---

## 1) Paper

### GET `/paper`

논문 목록 조회 (검색/필터/정렬)

- Auth: 필요
- Query
  - `q`: string (optional) - `title` + `short` 부분 일치
  - `tags`: int[] (optional) - 태그 ID, AND 조건
  - `source`: `arxiv` | `github` (optional)
  - `sort`: `popular` | `recent` (default: `recent`)
  - `limit`: int (1~100, default: 20)
  - `offset`: int (0+, default: 0)
- Response: `200`

```json
{
  "items": [
    {
      "paper": {
        "id": 3,
        "title": "...",
        "short": "...",
        "authors": ["A", "B"],
        "year": 2025,
        "image_url": "http://gomguk.cloud/papers/summary_58557.png",
        "raw_url": "http://gomguk.cloud/papers/paper_58557.pdf",
        "source": "arxiv",
        "tags": [11, 12],
        "is_liked": false,
        "is_scrapped": false,
        "like_count": 0,
        "scrap_count": 0,
        "recommend_score": null,
        "trending_score": null,
        "freshness_score": null
      }
    }
  ],
  "count": 1
}
```

### GET `/paper/feed`

추천 점수 기반 피드

- Auth: 필요
- Query
  - `limit`: int (1~100, default: 20)
  - `offset`: int (0+, default: 0)
- Response: `200` (`/paper`와 동일 구조)
- 비고
  - `recommend_score`, `trending_score`, `freshness_score`가 채워질 수 있음
  - `next_offset`, `has_more` 필드는 현재 응답에 없음

### GET `/paper/{paper_id}`

논문 상세 조회

- Auth: 필요
- Path
  - `paper_id`: int
- Response: `200` (`paper` 객체 단건)
- Errors: `404 PAPER_NOT_FOUND`

### PUT `/paper/{paper_id}/like`

좋아요 추가 (멱등)

- Auth: 필요
- Response: `204`
- Errors: `404 PAPER_NOT_FOUND`

### DELETE `/paper/{paper_id}/like`

좋아요 취소 (멱등)

- Auth: 필요
- Response: `204`
- Errors: `404 PAPER_NOT_FOUND`

### PUT `/paper/{paper_id}/scrap`

저장(스크랩) 추가 (멱등)

- Auth: 필요
- Response: `204`
- Errors: `404 PAPER_NOT_FOUND`

### DELETE `/paper/{paper_id}/scrap`

저장(스크랩) 취소 (멱등)

- Auth: 필요
- Response: `204`
- Errors: `404 PAPER_NOT_FOUND`

### PUT `/paper/{paper_id}/view`

읽음(조회) 기록 (멱등)

- Auth: 필요
- Response: `204`
- Errors: `404 PAPER_NOT_FOUND`

---

## 2) Me

### GET `/me`

내 정보 조회

- Auth: 필요
- Response: `200`

```json
{
  "id": 1,
  "provider": "google",
  "email": "user@example.com",
  "name": "g_12345",
  "profile_image": "http://gomguk.cloud/profiles/user-profiles/user_1_xxx.png",
  "meta": {},
  "counts": {
    "liked": 10,
    "saved": 4,
    "read": 22
  }
}
```

- `profile_image`가 없으면 `null`

### PUT `/me/profile-image`

프로필 이미지 업로드/수정 (PNG only)

- Auth: 필요
- Content-Type: `multipart/form-data`
- Body
  - `image`: file (`.png`)
- Response: `200`

```json
{
  "profile_image": "http://gomguk.cloud/profiles/user-profiles/user_1_xxx.png",
  "storage_path": "s3://profiles/user-profiles/user_1_xxx.png"
}
```

- Errors
  - `400 INVALID_FILE`
  - `401 AUTH_REQUIRED`

### PUT `/me/name`

이름 변경

- Auth: 필요
- Body (JSON)
  - `name`: string (trim 이후 1~100)
- Response: `200`

```json
{
  "name": "new_name"
}
```

- Errors
  - `400 INVALID_NAME`
  - `401 AUTH_REQUIRED`

### GET `/me/papers/liked`

좋아요한 논문 목록

- Auth: 필요
- Query: `limit`, `offset`
- Response: `200` (`PagedPapersResponse`)

### GET `/me/papers/saved`

저장한 논문 목록

- Auth: 필요
- Query: `limit`, `offset`
- Response: `200` (`PagedPapersResponse`)

### GET `/me/papers/read`

읽은 논문 목록

- Auth: 필요
- Query: `limit`, `offset`
- Response: `200` (`PagedPapersResponse`)

---

## 3) Tags

### GET `/tags`

태그 목록 조회

- Auth: 불필요
- Query
  - `limit`: int (1~500, default: 100)
  - `offset`: int (0+, default: 0)
- Response: `200`

---

## 4) Summary

### GET `/summary/{paper_id}`

논문 요약 조회

- Auth: 필요
- Path
  - `paper_id`: int
- Query
  - `style`: string (default: `plain`)
  - 허용값: `plain` | `detailed` | `dc` | `basic_aggro` | `instagram_card_news`
- Response: `200`

```json
{
  "style": "plain",
  "hook": "...",
  "points": ["...", "..."],
  "detailed": "..."
}
```

- Errors
  - `404 Paper not found`
  - `404 Summary not found`
  - `422 INVALID_STYLE`

---

## 5) OAuth/Auth

### GET `/oauth/{provider}/login`

OAuth 로그인 시작 (302)

- `provider`: `google` | `github`
- Query
  - `redirect_uri`: 로그인 완료 후 프론트로 이동할 URL
  - `remember`: boolean (default: false)
- 동작
  - state 쿠키 저장
  - provider authorize URL로 리다이렉트
- 비고
  - state 쿠키 path는 현재 `/api`
  - `INVALID_REDIRECT_URI` 검증은 현재 미구현

### GET `/oauth/{provider}/callback`

OAuth 콜백

- 동작
  - code/state 검증
  - 유저 조회/생성
  - `access_token`, `refresh_token` 쿠키 설정
  - `redirect_uri?is_new_user=...&access_token=...`로 302 이동

### POST `/auth/refresh`

Access 토큰 재발급

- Auth: `refresh_token` 쿠키 필요
- Response: `200`

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

- Errors
  - `401 AUTH_REQUIRED`
  - `401 INVALID_REFRESH`
  - `401 REFRESH_EXPIRED`
  - `500`

### POST `/auth/logout`

로그아웃

- Response: `204`
- 동작: auth 쿠키 제거

---

## 6) Event (디버그)

### GET `/event/recent`

최근 이벤트 조회

- Auth: 불필요
- Query
  - `limit`: int (1~200, default: 20)
- Response: `200`

---

## 7) Add (관리/적재용)

프론트 일반 사용자 기능보다는 데이터 적재/관리 성격 API입니다.

- POST `/add/tag`
- POST `/add/paper`
- POST `/add/summary`
- POST `/add/paper/{paper_id}/tags`

---

## Front Tips

- 쿠키 인증 사용 시 `fetch`에 `credentials: "include"` 필수
- 이미지 업로드 시 `FormData` 사용, JSON으로 보내지 않기
- `DELETE like/scrap`은 멱등이므로 이미 없는 상태여도 `204`가 정상
- `profile_image`는 `null`일 수 있으므로 기본 아바타 처리 필요
- `/paper`의 `sort=recommend`는 현재 미지원 (보내면 검증 에러)
