from fastapi import APIRouter, Body, Request
from typing import Optional

from app.api.deps import SessionDep, CurrentUser
from app.models.user import User

router = APIRouter()


@router.get("")
def mypage(user: CurrentUser) -> User:
    return user


@router.get("/recent-papers")
def recent_papers():
    return None


@router.get("/like-papers")
def like_papers():
    return None

@router.get("/scrap-papers")
def scrap_papers():
    return None
