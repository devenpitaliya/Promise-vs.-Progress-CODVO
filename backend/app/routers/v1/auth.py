from fastapi import APIRouter, status

from app.dependencies import ClientIP, CurrentUser
from app.dependencies.controllers import AuthCtl
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, ip: ClientIP, controller: AuthCtl) -> Token:
    return await controller.register(payload, ip)


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, ip: ClientIP, controller: AuthCtl) -> Token:
    return await controller.login(payload, ip)


@router.post("/demo", response_model=Token, status_code=status.HTTP_201_CREATED)
async def start_demo(ip: ClientIP, controller: AuthCtl) -> Token:
    return await controller.start_demo(ip)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
