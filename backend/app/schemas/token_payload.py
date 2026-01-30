from typing import Optional

from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: int
    exp: Optional[int] = None
    iat: Optional[int] = None