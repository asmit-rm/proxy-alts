from decimal import Decimal, ROUND_HALF_UP

from config import settings


def format_money(amount: Decimal | float | int) -> str:
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{settings.CURRENCY}{amount:.2f}"
