import logging
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories import UserRepository, normalise_email
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.services.auth_service import authenticate_user, create_user
from app.utils.exceptions import ConflictError, NotFoundError, RateLimitedError, UnauthorizedError
from app.utils.rate_limit import SlidingWindowLimiter
from app.utils.security import create_access_token

logger = logging.getLogger(__name__)

login_limiter = SlidingWindowLimiter(max_events=settings.LOGIN_ATTEMPTS_PER_MINUTE, window_seconds=60)
signup_limiter = SlidingWindowLimiter(max_events=settings.SIGNUPS_PER_HOUR_PER_IP, window_seconds=3600)


def _token_for(user: User) -> Token:
    return Token(access_token=create_access_token(str(user.id)), user=UserResponse.model_validate(user))


class AuthController:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, payload: UserCreate, ip: str) -> Token:
        if not signup_limiter.hit(ip):
            raise RateLimitedError("Too many sign-ups from this address. Try again later.")
        if await UserRepository(self.db).get_by_email(payload.email):
            raise ConflictError("An account with this email already exists.")
        user = await create_user(self.db, email=payload.email, password=payload.password, full_name=payload.full_name)
        logger.info("User %s registered from %s", user.id, ip)
        return _token_for(user)

    async def login(self, payload: UserLogin, ip: str) -> Token:
        if not login_limiter.hit(f"{ip}:{normalise_email(payload.email)}"):
            logger.warning("Sign-in rate limit hit from %s", ip)
            raise RateLimitedError("Too many sign-in attempts. Wait a minute and try again.")
        user = await authenticate_user(self.db, payload.email, payload.password)
        if user is None:
            logger.warning("Failed sign-in from %s", ip)
            raise UnauthorizedError("Incorrect email or password.")
        logger.info("User %s signed in from %s", user.id, ip)
        return _token_for(user)

    async def start_demo(self, ip: str) -> Token:
        """Create an isolated throwaway workspace. Only available when DEMO_MODE is enabled."""
        if not settings.DEMO_MODE:
            raise NotFoundError("Not found")
        if not signup_limiter.hit(f"demo:{ip}"):
            raise RateLimitedError("Too many demo workspaces from this address.")
        user = await create_user(
            self.db,
            email=f"demo-{secrets.token_hex(6)}@demo.invalid",
            password=secrets.token_urlsafe(24),
            full_name="Demo user",
            is_demo=True,
        )
        logger.info("Demo workspace %s created from %s", user.id, ip)
        return _token_for(user)
