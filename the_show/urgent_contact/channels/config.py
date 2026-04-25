from __future__ import annotations

import os
from typing import Dict, List, Optional


def telegram_bot_token() -> Optional[str]:
    return os.environ.get("URGENT_TELEGRAM_BOT_TOKEN")


def telegram_allowed_user_ids() -> List[str]:
    ids: List[str] = []
    for key in (
        "URGENT_CONTACT_PRIMARY_TELEGRAM_USER_ID",
        "URGENT_CONTACT_ALTERNATE_TELEGRAM_USER_ID",
    ):
        val = os.environ.get(key)
        if val:
            ids.append(val)
    return ids


def smtp_config() -> Optional[Dict[str, object]]:
    host = os.environ.get("URGENT_SMTP_HOST")
    if not host:
        return None
    return {
        "smtp_host": host,
        "smtp_port": int(os.environ.get("URGENT_SMTP_PORT", "587")),
        "username": os.environ.get("URGENT_SMTP_USERNAME", ""),
        "password": os.environ.get("URGENT_SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("URGENT_EMAIL_FROM", ""),
        "signing_secret": os.environ.get("URGENT_EMAIL_SIGNING_SECRET", ""),
    }


def link_base_url() -> str:
    host = os.environ.get("URGENT_LINK_ENDPOINT_HOST", "127.0.0.1")
    port = os.environ.get("URGENT_LINK_ENDPOINT_PORT", "5099")
    return f"http://{host}:{port}"


def whatsapp_config() -> Optional[Dict[str, str]]:
    access_token = os.environ.get("URGENT_WHATSAPP_ACCESS_TOKEN")
    if not access_token:
        return None
    return {
        "phone_number_id": os.environ.get("URGENT_WHATSAPP_PHONE_NUMBER_ID", ""),
        "access_token": access_token,
        "verify_token": os.environ.get("URGENT_WHATSAPP_VERIFY_TOKEN", ""),
    }


def twilio_config() -> Optional[Dict[str, str]]:
    account_sid = os.environ.get("URGENT_TWILIO_ACCOUNT_SID")
    if not account_sid:
        return None
    return {
        "account_sid": account_sid,
        "auth_token": os.environ.get("URGENT_TWILIO_AUTH_TOKEN", ""),
        "from_number": os.environ.get("URGENT_TWILIO_FROM_NUMBER", ""),
    }
