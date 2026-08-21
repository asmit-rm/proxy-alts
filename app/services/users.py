from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories import UserRepository
from config import settings


class UserService:
    def __init__(self, session: AsyncSession):
        self.repo = UserRepository(session)
        self.session = session

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> tuple[User, bool]:
        is_owner = telegram_id in settings.owner_ids
        return await self.repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_admin=is_owner,
        )

    async def get_user(self, telegram_id: int) -> User | None:
        return await self.repo.get_by_telegram_id(telegram_id)

    def format_balance(self, balance: Decimal) -> str:
        return f"{settings.CURRENCY}{balance:.2f}"
