from pydantic import BaseModel

class TokenPayload(BaseModel):
    sub: str | None = None
    exp: int | None = None
