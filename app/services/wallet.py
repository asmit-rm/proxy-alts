from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, WalletTransaction, WalletTransactionType
from app.database.repositories import UserRepository


class WalletService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_balance(self, telegram_id: int) -> Decimal:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return Decimal("0.00")
        return user.balance

    async def credit(
        self,
        telegram_id: int,
        amount: Decimal,
        tx_type: WalletTransactionType,
        description: str = None,
        reference_id: str = None,
        created_by: int = None,
    ) -> tuple[User, WalletTransaction]:
        """Add money to wallet"""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise ValueError("User not found")

        balance_before = user.balance
        balance_after = balance_before + amount

        user.balance = balance_after

        tx = WalletTransaction(
            user_id=user.id,
            type=tx_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_id=reference_id,
            description=description,
            created_by=created_by,
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(tx)

        return user, tx

    async def debit(
        self,
        telegram_id: int,
        amount: Decimal,
        tx_type: WalletTransactionType,
        description: str = None,
        reference_id: str = None,
        created_by: int = None,
    ) -> tuple[User, WalletTransaction]:
        """Remove money from wallet (never go negative)"""
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            raise ValueError("User not found")

        if user.balance < amount:
            raise ValueError("Insufficient balance")

        balance_before = user.balance
        balance_after = balance_before - amount

        user.balance = balance_after

        tx = WalletTransaction(
            user_id=user.id,
            type=tx_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_id=reference_id,
            description=description,
            created_by=created_by,
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(tx)

        return user, tx

    async def get_transactions(self, telegram_id: int, limit: int = 10) -> list[WalletTransaction]:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return []

        result = await self.session.execute(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user.id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
