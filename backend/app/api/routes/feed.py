from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def feed():
    return {"Hello": "feed"}
