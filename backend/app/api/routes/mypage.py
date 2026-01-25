from fastapi import APIRouter, Body, Request

from app.api.deps import SessionDep
from app.models import *

router = APIRouter()


@router.get("")
def mypage():
    return None


@router.get("/recent-papers")
def recent_papers():
    return None


@router.get("/like-papers")
def like_papers():
    return None

@router.get("/scrap-papers")
def scrap_papers():
    return None
