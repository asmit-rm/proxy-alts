import os
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import StringSession

from config import settings
from app.utils.logger import logger

# Sessions folder
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


class FulfillmentProvider:
    """
    Handles number login, session management, code detection and delivery.
    Completely separated from marketplace logic.
    """

    def __init__(self):
        self.api_id = settings.API_ID
        self.api_hash = settings.API_HASH

    def _get_session_path(self, phone: str) -> Path:
        # Clean phone number for filename
        clean = phone.replace("+", "").replace(" ", "")
        return SESSIONS_DIR / f"{clean}.session"

    async def start_login(self, phone: str) -> dict:
        """
        Start login process for a number.
        Returns client and phone_code_hash.
        """
        session_path = self._get_session_path(phone)
        client = TelegramClient(str(session_path), self.api_id, self.api_hash)

        await client.connect()

        if await client.is_user_authorized():
            await client.disconnect()
            return {"status": "already_logged_in", "phone": phone}

        result = await client.send_code_request(phone)

        return {
            "status": "code_sent",
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
            "client": client,  # Keep client alive until code is entered
        }

    async def complete_login(
        self,
        client: TelegramClient,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str = None,
    ) -> dict:
        """
        Complete login with the code provided by owner.
        """
        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not password:
                return {"status": "2fa_required"}
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            return {"status": "invalid_code"}
        except Exception as e:
            logger.error("Login failed for %s: %s", phone, e)
            return {"status": "error", "message": str(e)}

        # Successfully logged in
        me = await client.get_me()
        await client.disconnect()

        logger.info("Number logged in successfully: %s (user_id=%s)", phone, me.id)

        return {
            "status": "success",
            "phone": phone,
            "telegram_user_id": me.id,
            "session_file": str(self._get_session_path(phone)),
        }

    async def get_code(self, phone: str) -> str | None:
        """
        Get the latest login code from the number (for buyer).
        This is a simplified version - in production we listen for new messages.
        """
        session_path = self._get_session_path(phone)
        if not session_path.exists():
            return None

        client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return None

        # Get recent messages from Telegram / 777000
        try:
            messages = await client.get_messages(777000, limit=5)
            for msg in messages:
                if msg.text and ("code" in msg.text.lower() or msg.text.isdigit()):
                    # Extract code (simple version)
                    import re
                    codes = re.findall(r'\b\d{5,6}\b', msg.text)
                    if codes:
                        await client.disconnect()
                        return codes[0]
        except Exception as e:
            logger.error("Error getting code for %s: %s", phone, e)

        await client.disconnect()
        return None

    async def logout(self, phone: str) -> bool:
        """
        Logout / delete session for a number.
        """
        session_path = self._get_session_path(phone)

        try:
            if session_path.exists():
                client = TelegramClient(str(session_path), self.api_id, self.api_hash)
                await client.connect()
                if await client.is_user_authorized():
                    await client.log_out()
                await client.disconnect()
                session_path.unlink(missing_ok=True)
                logger.info("Logged out and deleted session: %s", phone)
                return True
        except Exception as e:
            logger.error("Logout failed for %s: %s", phone, e)

        return False
