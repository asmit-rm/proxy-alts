from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Product, ProductStatus


class ProductService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_available_countries(self) -> list[str]:
        """Return countries that have at least 1 active product with stock > 0"""
        result = await self.session.execute(
            select(Product.country)
            .where(
                Product.status == ProductStatus.ACTIVE,
                Product.stock > 0,
            )
            .distinct()
            .order_by(Product.country)
        )
        return [row[0] for row in result.all()]

    async def get_qualities_by_country(self, country: str) -> list[str]:
        """Return available qualities for a country that have stock"""
        result = await self.session.execute(
            select(Product.quality)
            .where(
                Product.country == country,
                Product.status == ProductStatus.ACTIVE,
                Product.stock > 0,
            )
            .distinct()
            .order_by(Product.quality)
        )
        return [row[0] for row in result.all()]

    async def get_products(
        self,
        country: str,
        quality: str,
    ) -> list[Product]:
        """Get active products for country + quality"""
        result = await self.session.execute(
            select(Product)
            .where(
                Product.country == country,
                Product.quality == quality,
                Product.status == ProductStatus.ACTIVE,
                Product.stock > 0,
            )
            .order_by(Product.price)
        )
        return list(result.scalars().all())

    async def get_product_by_id(self, product_id: int) -> Product | None:
        result = await self.session.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_all_products(self) -> list[Product]:
        result = await self.session.execute(
            select(Product).order_by(Product.country, Product.quality)
        )
        return list(result.scalars().all())
