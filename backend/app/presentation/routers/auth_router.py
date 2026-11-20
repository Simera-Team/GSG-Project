
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.RequestDto.register_dto import RegisterRequest
from app.application.dto.ResponseDto.user_response import RegisterResponse

from app.application.dto.RequestDto.login_dto import LoginRequest 
from app.application.dto.ResponseDto.login_response import LoginResponse

from app.application.services.auth_service import AuthService
from app.core.dependencies import CurrentUser, get_auth_service
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


@router.get(
    "/me",
    response_model=RegisterResponse,
    status_code=status.HTTP_200_OK
)
def me(user: CurrentUser):
    return user
