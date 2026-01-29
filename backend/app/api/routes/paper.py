import requests
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import RedirectResponse

from app.api.deps import SessionDep, TokenDep, CurrentUser
from app.core.config import settings
from app.schemas.PaperRead import PaperRead
from app.crud import get_paper_by_id, add_userpaperlike


router = APIRouter()

GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI


@router.get("/{paper_id}")
def get_paper(paper_id, session: SessionDep) -> Optional[PaperRead]:
    try :
        paper = get_paper_by_id(session, paper_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.put("/{paper_id}/like")
def like_paper(paper_id: int, session: SessionDep, user: CurrentUser):
    try :
        paper = get_paper_by_id(session, paper_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    result = add_userpaperlike(session, user, paper)
    if result == "exists":
        raise HTTPException(status_code=409, detail="Already liked")
    if result == "db_error":
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    return None

# @router.delete("/{paper_id}/like")
# @router.put("/{paper_id}/scrap")
# @router.delete("/{paper_id}/scrap")
