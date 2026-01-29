import requests
from datetime import timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from starlette.responses import RedirectResponse

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.security import create_access_token
from app.core.enums import AuthProvider
from app.models import User
from app.crud import get_user_by_sub, create_user

router = APIRouter()

GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI


@router.get("/google/login")
def google_login():
    params = {"client_id": GOOGLE_CLIENT_ID,
              "redirect_uri": GOOGLE_REDIRECT_URI,
              "response_type": "code",
              "scope": "openid email profile",
    }
    return RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?"
        +urlencode(params)
    )


@router.get("/google/callback")
def google_callback(code: str, session: SessionDep):
    #code -> token 교환
    token_endpoint = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    response = requests.post(token_endpoint, data=data, timeout=10)
    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to obtain token: {response.status_code} {response.text}")
    token_json = response.json()
    raw_id_token = token_json.get("id_token")
    if raw_id_token is None:
        raise HTTPException(status_code=400, detail="no id_token")

    #token -> sub 교환
    payload = google_id_token.verify_oauth2_token(
        raw_id_token,
        google_requests.Request(),
        GOOGLE_CLIENT_ID,
    )
    google_sub = payload["sub"]
    email = payload.get("email")
    if email is None:
        raise HTTPException(status_code=400, detail="No email from Google")

    #google_sub db 조회
    user = get_user_by_sub(
        session = session,
        provider = AuthProvider.google,
        provider_sub = google_sub
    )

    is_new_user = False
    if user is None: #user 생성
        created = create_user(
            session = session,
            provider = AuthProvider.google,
            provider_sub = google_sub,
            email = email,
            nickname = f"g_{google_sub[:10]}"
        )
        if created is not None:
            user = created
            is_new_user = True
        else:
            user = get_user_by_sub(
                session = session,
                provider=AuthProvider.google,
                provider_sub=google_sub
            )
            if user is None:
                raise HTTPException(status_code=409, detail="user create error")
            is_new_user = False

    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=60)
    )

    return {"access_token": token, "token_type": "bearer", "is_new_user": is_new_user}
