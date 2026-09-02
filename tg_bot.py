import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Message
from aiogram.filters import Command
from config import TG_BOT_TOKEN, TG_USER_ID, TG_PROXY

def _create_bot() -> Bot:
    if TG_PROXY:
        print(f"Telegram: используем прокси {TG_PROXY}")
        session = AiohttpSession(proxy=TG_PROXY)
        return Bot(token=TG_BOT_TOKEN, session=session)
    return Bot(token=TG_BOT_TOKEN)

bot = _create_bot()
dp = Dispatcher()

# Поллинг отключается после сетевого сбоя, чтобы не блокировать Ctrl+C
_polling_enabled = True

def _tg_configured() -> bool:
    return (
        TG_BOT_TOKEN not in ("YOUR_BOT_TOKEN_HERE", "your_bot_token_here", "")
        and TG_USER_ID not in ("YOUR_USER_ID_HERE", "your_telegram_id_here", "")
    )

async def send_notification(text: str):
    """Отправляет уведомление пользователю."""
    if not _tg_configured() or not _polling_enabled:
        print("TG:", text)
        return

    try:
        await asyncio.wait_for(
            bot.send_message(chat_id=TG_USER_ID, text=text, parse_mode="HTML"),
            timeout=10,
        )
    except Exception as e:
        print(f"Ошибка при отправке сообщения в TG: {e}")
        print("TG:", text)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if str(message.from_user.id) == TG_USER_ID:
        await message.answer("Привет! Я ваш ИИ-агент для поиска работы на HH.ru. Я буду присылать сюда уведомления.")
    else:
        await message.answer(f"Извините, у вас нет доступа к этому боту.\nВаш ID: <code>{message.from_user.id}</code>\nСкопируйте его и пропишите в файл .env как TG_USER_ID, после чего перезапустите скрипт.")

captcha_event = asyncio.Event()
captcha_solution = ""

async def send_captcha_request(filepath: str, text: str):
    """Отправляет фото капчи пользователю."""
    if not _tg_configured() or not _polling_enabled:
        print("ОШИБКА: Telegram недоступен. Капча сохранена в", filepath)
        return

    try:
        from aiogram.types import FSInputFile
        photo = FSInputFile(filepath)
        captcha_event.clear()
        await asyncio.wait_for(
            bot.send_photo(chat_id=TG_USER_ID, photo=photo, caption=text, parse_mode="HTML"),
            timeout=15,
        )
    except Exception as e:
        print(f"Ошибка при отправке капчи в TG: {e}")

@dp.message()
async def handle_text(message: Message):
    """Принимает текст капчи от пользователя."""
    if str(message.from_user.id) != TG_USER_ID:
        return

    global captcha_solution
    if not captcha_event.is_set():
        captcha_solution = message.text.strip()
        captcha_event.set()
        await message.answer("✅ Код принят, пробую ввести...")

async def stop_bot():
    """Корректно останавливает polling."""
    try:
        await asyncio.wait_for(dp.stop_polling(), timeout=2)
    except Exception:
        pass
    try:
        await asyncio.wait_for(bot.session.close(), timeout=2)
    except Exception:
        pass

async def start_bot(stop_event: asyncio.Event | None = None):
    """Запускает бота. При недоступности Telegram — не ретраит бесконечно."""
    global _polling_enabled
    print("Запуск Telegram-бота...")

    if not _tg_configured():
        print("Telegram не настроен — уведомления только в консоль.")
        if stop_event:
            await stop_event.wait()
        return

    # Быстрая проверка связи (не ждём минуту)
    try:
        await asyncio.wait_for(bot.get_me(), timeout=8)
    except (asyncio.TimeoutError, TelegramNetworkError, OSError, Exception) as e:
        _polling_enabled = False
        print(
            f"⚠️ Telegram недоступен ({e}).\n"
            f"   Polling отключён, чтобы не мешать работе и Ctrl+C.\n"
            f"   Включите VPN или добавьте в .env: TG_PROXY=socks5://127.0.0.1:1080\n"
            f"   Уведомления будут в консоли."
        )
        if stop_event:
            await stop_event.wait()
        return

    print("✅ Telegram подключён.")
    try:
        polling = asyncio.create_task(dp.start_polling(bot), name="tg-polling")
        if stop_event:
            stop_waiter = asyncio.create_task(stop_event.wait(), name="tg-stop")
            done, _ = await asyncio.wait(
                {polling, stop_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_waiter in done:
                polling.cancel()
                try:
                    await asyncio.wait_for(polling, timeout=2)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            else:
                stop_waiter.cancel()
        else:
            await polling
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"⚠️ Telegram polling остановлен: {e}")

if __name__ == "__main__":
    asyncio.run(start_bot())
