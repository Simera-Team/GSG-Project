
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.application.dto.RequestDto.register_dto import RegisterRequest
from app.application.dto.ResponseDto.user_response import RegisterResponse

from app.application.dto.RequestDto.login_dto import LoginRequest 
from app.application.dto.ResponseDto.login_response import LoginResponse

from app.application.services.auth_service import AuthService
from app.core.dependencies import get_auth_service
from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK
)
def login(
    data: LoginRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service)
    ]
):
    try:
        return service.login(data)

    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"}
        ) from exc


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    data: RegisterRequest,
    service: Annotated[
        AuthService,
        Depends(get_auth_service)
    ]
):
    try:
        return service.register(data)

    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc)
        ) from exc


@router.post(
    "/token",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Login for Swagger's Authorize button",
)
def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[
        AuthService,
        Depends(get_auth_service)
    ]
):
    """Same login as /auth/login, but takes the form fields Swagger sends
    (put the e-mail in `username`). Apps should keep using /auth/login."""
    try:
        return service.login(LoginRequest(email=form.username, password=form.password))

    except (InvalidCredentialsError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        ) from exc
