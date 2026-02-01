from fastapi import APIRouter

from app.api.routes import paper, summary, tags, oauth, me, auth, add, event


api_router = APIRouter(prefix="/api")

api_router.include_router(paper.router, prefix="/paper", tags=["paper"])
api_router.include_router(summary.router, prefix="/summary", tags=["summary"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(add.router, prefix="/add", tags=["add"])
api_router.include_router(event.router, prefix="/event", tags=["event"])