from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Order,
    OrderStatus,
    Product,
    ProductStatus,
    StockNumber,
    StockStatus,
    User,
    WalletTransactionType,
)
from app.services.wallet import WalletService


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.wallet_service = WalletService(session)

    async def create_order_atomic(
        self,
        telegram_id: int,
        product_id: int,
    ) -> Order:
        """
        Atomic purchase:
        - Lock product + available stock number
        - Check stock + active
        - Check balance
        - Deduct balance
        - Assign one StockNumber
        - Create order
        - Decrease product.stock
        """
        # Get user
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        # Get product with lock
        result = await self.session.execute(
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ValueError("Product not found")

        if product.status != ProductStatus.ACTIVE:
            raise ValueError("Product is not available")

        if product.stock <= 0:
            raise ValueError("Out of stock")

        # Get one available stock number with lock
        result = await self.session.execute(
            select(StockNumber)
            .where(
                StockNumber.product_id == product_id,
                StockNumber.status == StockStatus.AVAILABLE,
            )
            .with_for_update()
            .limit(1)
        )
        stock_number = result.scalar_one_or_none()

        if not stock_number:
            raise ValueError("Out of stock")

        if user.balance < product.price:
            raise ValueError("Insufficient balance")

        # Deduct balance
        await self.wallet_service.debit(
            telegram_id=telegram_id,
            amount=product.price,
            tx_type=WalletTransactionType.PURCHASE,
            description=f"Purchase product #{product.id}",
            reference_id=str(product.id),
        )

        # Mark number as sold
        stock_number.status = StockStatus.SOLD
        stock_number.sold_at = datetime.now(timezone.utc)

        # Decrease product stock
        product.stock -= 1
        if product.stock <= 0:
            product.status = ProductStatus.SOLD_OUT

        # Create order
        order = Order(
            user_id=user.id,
            product_id=product.id,
            country=product.country,
            quality=product.quality,
            product_name=product.name,
            amount=product.price,
            status=OrderStatus.COMPLETED,
            fulfillment_data=stock_number.phone,
        )
        self.session.add(order)
        await self.session.flush()  # get order.id

        stock_number.order_id = order.id

        await self.session.commit()
        await self.session.refresh(order)

        return order

    async def get_user_orders(self, telegram_id: int, limit: int = 20) -> list[Order]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return []

        result = await self.session.execute(
            select(Order)
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_order(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def update_order_status(
        self,
        order_id: int,
        status: OrderStatus,
        fulfillment_data: str = None,
    ) -> Order:
        order = await self.get_order(order_id)
        if not order:
            raise ValueError("Order not found")

        order.status = status
        if fulfillment_data is not None:
            order.fulfillment_data = fulfillment_data

        await self.session.commit()
        await self.session.refresh(order)
        return order
