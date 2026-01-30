from fastapi import APIRouter

from fastapi.responses import HTMLResponse

from app.api.routes import paper, summary, tags, oauth, me, auth

api_router = APIRouter(prefix="/api")


api_router.include_router(paper.router, prefix="/paper", tags=["paper"])
api_router.include_router(summary.router, prefix="/summary", tags=["summary"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])


@api_router.get("/dev/redirect", response_class=HTMLResponse)
def dev_redirect(is_new_user: str = "false"):
    return f"""
    <h1>OAuth Done</h1>
    <p>is_new_user = {is_new_user}</p>
    <p>Check cookies: refresh_token</p>
    """