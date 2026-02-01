from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.enums import AuthProvider, EventType
from app.crud.user import get_user_by_sub, create_user
from app.crud.event import create_event

router = APIRouter()

ProviderName = Literal["google", "github"]

STATE_COOKIE_KEY = "oauth_state"
STATE_TTL_SECONDS = 10 * 60

REFRESH_COOKIE_KEY = "refresh_token"
REFRESH_DAYS_DEFAULT = 1
REFRESH_DAYS_REMEMBER = 7


# =========================
# /api/oauth/{provider}/login
# =========================
@router.get(
    "/{provider}/login",
    summary="OAuth 로그인 시작",
    description=(
        "OAuth 로그인 플로우를 시작한다.\n"
        "- state(redirect_uri, remember 포함)를 쿠키에 저장\n"
        "- provider authorize URL로 302 리다이렉트\n\n"
        "Query:\n"
        "- redirect_uri: 로그인 완료 후 이동할 프런트 URL\n"
        "- remember: 로그인 유지 (true면 refresh 7일, false면 1일)"
    ),
    responses={
        302: {"description": "Provider authorize URL로 리다이렉트"},
        404: {"description": "지원하지 않는 provider"},
        500: {"description": "OAuth 환경변수 미설정"},
    },
)
def oauth_login(
    provider: str,
    redirect_uri: str = Query(..., description="로그인 성공 후 돌아갈 프런트 URL"),
    remember: bool = Query(False, description="로그인 유지"),
):
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Provider not found")

    backend_public_url = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
    if not backend_public_url:
        raise HTTPException(status_code=500, detail="BACKEND_PUBLIC_URL is not configured")

    secure_cookie = backend_public_url.startswith("https://")

    # state 만들기(서명)
    now = datetime.now(timezone.utc)
    state_payload = {
        "redirect_uri": redirect_uri,
        "remember": remember,
        "nonce": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=STATE_TTL_SECONDS)).timestamp()),
    }
    state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    # 공통 callback url (백엔드가 /api prefix도 갖는 방식)
    callback_url = f"{backend_public_url}/api/oauth/{provider}/callback"

    # provider authorize URL 만들기
    if provider == "google":
        if not getattr(settings, "GOOGLE_CLIENT_ID", None):
            raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        location = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    else:
        if not getattr(settings, "GITHUB_CLIENT_ID", None):
            raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID is not configured")

        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "read:user user:email",
            "state": state,
        }
        location = "https://github.com/login/oauth/authorize?" + urlencode(params)

    resp = RedirectResponse(url=location, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(
        key=STATE_COOKIE_KEY,
        value=state,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/api/oauth",
    )
    return resp


# =========================
# /api/oauth/{provider}/callback
# =========================
@router.get(
    "/{provider}/callback",
    summary="OAuth 콜백",
    description=(
        "Provider가 redirect_uri로 호출하는 콜백.\n"
        "- state 쿠키와 query state 비교\n"
        "- code로 토큰 교환 후 provider_sub/email 획득\n"
        "- 유저 없으면 임시 닉네임으로 생성\n"
        "- refresh_token(영속 쿠키, 1일/7일) 설정\n"
        "- redirect_uri로 302 리다이렉트하며 is_new_user 전달"
    ),
    responses={
        302: {"description": "프런트 redirect_uri로 리다이렉트"},
        400: {"description": "요청 누락/토큰 교환 실패/email 없음 등"},
        401: {"description": "INVALID_STATE"},
        404: {"description": "지원하지 않는 provider"},
        409: {"description": "user create error"},
        500: {"description": "OAuth 환경변수 미설정"},
    },
)
async def oauth_callback(
    provider: str,
    session: SessionDep,
    request: Request,
    code: Optional[str] = Query(None, description="authorization code"),
    state: Optional[str] = Query(None, description="state"),
    error: Optional[str] = Query(None, description="provider error"),
):
    if provider not in ("google", "github"):
        raise HTTPException(status_code=404, detail="Provider not found")

    if error:
        raise HTTPException(status_code=400, detail=f"OAUTH_ERROR: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="OAUTH_ERROR: missing code/state")

    backend_public_url = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
    if not backend_public_url:
        raise HTTPException(status_code=500, detail="BACKEND_PUBLIC_URL is not configured")
    secure_cookie = backend_public_url.startswith("https://")

    # state 쿠키 검증(최소)
    cookie_state = request.cookies.get(STATE_COOKIE_KEY)
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=401, detail="INVALID_STATE")

    # state decode해서 redirect_uri/remember 꺼내기
    try:
        state_payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        redirect_uri = str(state_payload["redirect_uri"])
        remember = bool(state_payload.get("remember", False))
    except Exception:
        raise HTTPException(status_code=401, detail="INVALID_STATE")

    ttl_days = REFRESH_DAYS_REMEMBER if remember else REFRESH_DAYS_DEFAULT
    callback_url = f"{backend_public_url}/api/oauth/{provider}/callback"

    # -------------------------
    # provider_sub/email 획득
    # -------------------------
    provider_sub: str
    email: str

    if provider == "google":
        if not getattr(settings, "GOOGLE_CLIENT_ID", None) or not getattr(settings, "GOOGLE_CLIENT_SECRET", None):
            raise HTTPException(status_code=500, detail="Google OAuth is not configured")

        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(token_url, data=data)

        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to obtain token: {token_resp.status_code}")

        token_json = token_resp.json()
        raw_id_token = token_json.get("id_token")
        if raw_id_token is None:
            raise HTTPException(status_code=400, detail="no id_token")

        payload = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        provider_sub = str(payload.get("sub") or "")
        email = payload.get("email") or ""
        if not provider_sub:
            raise HTTPException(status_code=400, detail="No sub from Google")
        if not email:
            raise HTTPException(status_code=400, detail="No email from Google")

        provider_enum = AuthProvider.google
        nick_prefix = "g_"

    else:
        if not getattr(settings, "GITHUB_CLIENT_ID", None) or not getattr(settings, "GITHUB_CLIENT_SECRET", None):
            raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")

        # 1) code -> access_token
        token_url = "https://github.com/login/oauth/access_token"
        data = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": callback_url,
        }
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(token_url, data=data, headers=headers)

            if token_resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Failed to obtain token: {token_resp.status_code}")

            token_json = token_resp.json()
            access_token = token_json.get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="no access_token")

            # 2) /user
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")
            user_json = user_resp.json()
            gh_id = user_json.get("id")
            if gh_id is None:
                raise HTTPException(status_code=400, detail="No id from GitHub")
            provider_sub = str(gh_id)

            # 3) /user/emails
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if emails_resp.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch GitHub emails")

            emails = emails_resp.json()
            email = ""
            if isinstance(emails, list) and emails:
                primary = next((e for e in emails if e.get("primary")), None)
                verified = next((e for e in emails if e.get("verified")), None)
                chosen = primary or verified or emails[0]
                email = chosen.get("email") or ""

            if not email:
                raise HTTPException(status_code=400, detail="No email from GitHub")

        provider_enum = AuthProvider.github
        nick_prefix = "gh_"

    user = get_user_by_sub(
        session=session,
        provider=provider_enum,
        provider_sub=provider_sub,
    )

    is_new_user = False
    if user is None:
        created = create_user(
            session=session,
            provider=provider_enum,
            provider_sub=provider_sub,
            email=email,
            name=f"{nick_prefix}{provider_sub[:10]}",
        )
        if created is not None:
            user = created
            is_new_user = True
        else:
            user = get_user_by_sub(session=session, provider=provider_enum, provider_sub=provider_sub)
            if user is None:
                raise HTTPException(status_code=409, detail="user create error")
            is_new_user = False

    # -------------------------
    # refresh 쿠키 + redirect
    # -------------------------
    now = datetime.now(timezone.utc)
    refresh_payload = {
        "sub": str(user.id),
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
    }
    refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    refresh_max_age = int(timedelta(days=ttl_days).total_seconds())

    # redirect_uri에 is_new_user 붙이기
    sep = "&" if "?" in redirect_uri else "?"
    final_redirect = f"{redirect_uri}{sep}is_new_user={str(is_new_user).lower()}"

    resp = RedirectResponse(url=final_redirect, status_code=status.HTTP_302_FOUND)

    # state 1회용 삭제
    resp.delete_cookie(key=STATE_COOKIE_KEY, path="/api/oauth")

    # refresh는 영속 쿠키
    resp.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/api",
    )

    if is_new_user:
        create_event(
            session,
            user_id=user.id,
            event_type=EventType.create_user,
            meta={"provider": provider},
        )
    create_event(
        session,
        user_id=user.id,
        event_type=EventType.login,
        meta={"provider": provider},
    )
    session.commit()

    return resp
