from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from auth.passwords import verify_password
from auth.tokens import create_access_token
from database.session import get_db
from models.user import User
from schemas.auth import AuthenticatedUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(login_in: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.phone == login_in.phone)).first()
    if user is None or not verify_password(login_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = getattr(user.role, "value", user.role)
    return TokenResponse(access_token=create_access_token(user.id, role))


@router.get("/me", response_model=AuthenticatedUser)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user