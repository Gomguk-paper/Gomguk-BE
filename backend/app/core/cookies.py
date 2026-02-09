from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from app.core.config import settings


def _normalize_url(value: str) -> str:
    if not value:
        return ""
    if "://" not in value:
        return f"http://{value}"
    return value


def _scheme_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.url.scheme


def get_cookie_settings(
    *,
    request: Request | None = None,
    redirect_uri: str | None = None,
) -> tuple[bool, str]:
    backend_public_url = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
    frontend_host = getattr(settings, "FRONTEND_HOST", "").rstrip("/")

    scheme = _scheme_from_request(request)
    secure_cookie = False
    if scheme:
        secure_cookie = scheme == "https"
    elif backend_public_url:
        secure_cookie = backend_public_url.startswith("https://")

    if redirect_uri and redirect_uri.startswith("https://"):
        secure_cookie = True
    same_site = "lax"

    if backend_public_url and (frontend_host or redirect_uri):
        backend = urlparse(_normalize_url(backend_public_url))
        frontend = urlparse(_normalize_url(redirect_uri or frontend_host))
        if backend.hostname and frontend.hostname:
            cross_site = backend.hostname != frontend.hostname or (
                backend.scheme and frontend.scheme and backend.scheme != frontend.scheme
            )
            if cross_site:
                same_site = "none"

    if same_site == "none" and not secure_cookie:
        same_site = "lax"

    return secure_cookie, same_site
