from config import ENABLE_TELEGRAM


async def notify(text: str):
    """Уведомление: консоль или Telegram."""
    if ENABLE_TELEGRAM:
        from tg_bot import send_notification
        await send_notification(text)
    else:
        print(text)
