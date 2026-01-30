from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/dev/redirect", response_class=HTMLResponse)
def dev_redirect(is_new_user: str = "false"):
    return f"""
    <h1>OAuth Done</h1>
    <p>is_new_user = {is_new_user}</p>
    <p>Check cookies: refresh_token</p>
    """
