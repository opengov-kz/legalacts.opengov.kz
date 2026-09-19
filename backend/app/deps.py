from typing import Iterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_api_key(request: Request, x_api_key: str = Header(...)) -> None:
    if x_api_key != request.app.state.settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
