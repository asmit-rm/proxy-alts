from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Payment, PaymentStatus, User, WalletTransactionType
from app.services.wallet import WalletService


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.wallet_service = WalletService(session)

    async def create_payment(
        self,
        user_id: int,          # DB user.id
        amount: Decimal,
        screenshot_file_id: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            amount=amount,
            screenshot_file_id=screenshot_file_id,
            status=PaymentStatus.PENDING,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_payment(self, payment_id: int) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_payments(self) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def approve_payment(
        self,
        payment_id: int,
        reviewer_id: int,
    ) -> tuple[Payment, User]:
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError("Payment not found")

        if payment.status != PaymentStatus.PENDING:
            raise ValueError("Payment already processed")

        # Get user by DB id
        result = await self.session.execute(
            select(User).where(User.id == payment.user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        # Credit wallet
        user, tx = await self.wallet_service.credit(
            telegram_id=user.telegram_id,
            amount=payment.amount,
            tx_type=WalletTransactionType.DEPOSIT,
            description=f"Payment #{payment.id} approved",
            reference_id=str(payment.id),
            created_by=reviewer_id,
        )

        # Update payment
        payment.status = PaymentStatus.APPROVED
        payment.reviewed_by = reviewer_id
        payment.reviewed_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(payment)
        await self.session.refresh(user)

        return payment, user

    async def reject_payment(
        self,
        payment_id: int,
        reviewer_id: int,
    ) -> Payment:
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError("Payment not found")

        if payment.status != PaymentStatus.PENDING:
            raise ValueError("Payment already processed")

        payment.status = PaymentStatus.REJECTED
        payment.reviewed_by = reviewer_id
        payment.reviewed_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(payment)

        return payment
