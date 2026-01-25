from fastapi import APIRouter

from app.api.routes import feed, mypage, onboarding, search, oauth, paper

api_router = APIRouter()

api_router.include_router(feed.router, prefix="/feed", tags=["feed"])
api_router.include_router(mypage.router, prefix="/mypage", tags=["mypage"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(paper.router, prefix="/paper", tags=["paper"])

@api_router.get("/")
def home():
    return {"hi"}
