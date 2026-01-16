from fastapi import APIRouter

from app.api.routes import feed, mypage, onboarding, search, oauth
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(feed.router)
api_router.include_router(mypage.router)
api_router.include_router(onboarding.router)
api_router.include_router(search.router)
api_router.include_router(oauth.router)


# if settings.ENVIRONMENT == "local":
#     api_router.include_router(private.router)