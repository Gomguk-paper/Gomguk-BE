import requests
from datetime import timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from starlette.responses import RedirectResponse

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserAuthIdentity, AuthProvider

router = APIRouter(prefix="/oauth")

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
    response = requests.post(token_endpoint, data=data)
    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to obtain token: {response.status_code} {response.text}")
    token_json = response.json()
    raw_id_token = token_json.get("id_token")
    if not raw_id_token:
        raise HTTPException(status_code=400, detail="no id_token")

    #token -> sub 교환
    payload = google_id_token.verify_oauth2_token(
        raw_id_token,
        google_requests.Request(),
        GOOGLE_CLIENT_ID,
    )
    google_sub = payload["sub"]
    email = payload.get("email")

    #google_sub db 조회
    identity = session.exec(
        select(UserAuthIdentity).where(
            UserAuthIdentity.provider == AuthProvider.google,
            UserAuthIdentity.provider_user_id == google_sub,
        )
    ).first()

    is_new_user = False
    if identity:
        user = identity.user
    else: #user 생성
        is_new_user = True

        nickname = f"g_{google_sub[:10]}"
        user = User(email=email, nickname=nickname)
        session.add(user)
        session.flush()

        identity = UserAuthIdentity(
            user_id=user.id,
            provider=AuthProvider.google,
            provider_user_id=google_sub,
            email=email,
        )
        session.add(identity)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            identity = session.exec(
                select(UserAuthIdentity).where(
                    UserAuthIdentity.provider == AuthProvider.google,
                    UserAuthIdentity.provider_user_id == google_sub,
                )
            ).first()
            if not identity:
                raise
            user = identity.user
            is_new_user = False

    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=60)
    )

    return {"access_token": token, "token_type": "bearer", "is_new_user": is_new_user}
