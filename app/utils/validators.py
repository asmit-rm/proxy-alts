from config import settings


def is_owner(telegram_id: int) -> bool:
    return telegram_id in settings.owner_ids
