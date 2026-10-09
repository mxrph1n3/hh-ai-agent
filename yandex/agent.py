import asyncio
import os
import signal

from agent.notify import notify
from ai.analyzer import check_ollama
from ai.yandex_analyzer import generate_reply, is_order_suitable
from config import (
    YANDEX_DRY_RUN,
    YANDEX_LOOP_MINUTES,
    YANDEX_MAX_REPLIES,
    YANDEX_ORDERS_URL,
)
from storage.db import (
    add_yandex_order,
    count_yandex_replies_today,
    init_yandex_db,
    is_yandex_seen,
)
from yandex.apply import read_order_text, send_reply
from yandex.auth import ensure_logged_in
from yandex.browser import BrowserSession
from yandex.feed import collect_orders
from yandex.filters import reject_reason
from yandex.text import sanitize_reply


async def run(stop_event: asyncio.Event):
    session = BrowserSession()
    try:
        try:
            await session.start()
        except Exception as e:
            print(f"❌ Не удалось запустить браузер: {e}")
            stop_event.set()
            return

        if not await ensure_logged_in(session, YANDEX_ORDERS_URL):
            print("❌ Вход в Яндекс Исполнители не выполнен.")
            stop_event.set()
            return

        mode = "проверка без отправки" if YANDEX_DRY_RUN else "боевые отклики"
        await notify(f"яндекс исполнители запущены. режим: {mode}.")

        while not stop_event.is_set():
            try:
                await _cycle(session)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Ошибка цикла: {e}")

            print(f"Ожидание {YANDEX_LOOP_MINUTES} мин...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=YANDEX_LOOP_MINUTES * 60)
                break
            except asyncio.TimeoutError:
                pass
    finally:
        print("Закрываем браузер...")
        await session.stop()


async def _cycle(session: BrowserSession):
    page = session.page
    print("Обновляем ленту заказов...")
    await page.goto(YANDEX_ORDERS_URL, wait_until="domcontentloaded", timeout=60000)
    orders = await collect_orders(page)
    print(f"Заказов на ленте: {len(orders)}")

    sent_today = count_yandex_replies_today()
    print(f"Откликов сегодня: {sent_today}/{YANDEX_MAX_REPLIES}")

    for order in orders:
        if stop_event_set():
            return
        if is_yandex_seen(order["id"]):
            continue

        reason = reject_reason(f"{order['title']}\n{order['preview']}")
        if reason:
            print(f"⏩ Мимо [{reason}]: {order['title']}")
            add_yandex_order(order["id"], order["title"], order["url"], "rejected")
            continue

        if sent_today >= YANDEX_MAX_REPLIES and not YANDEX_DRY_RUN:
            print("Лимит откликов на сегодня исчерпан.")
            return

        await _handle_order(session, order)
        if not YANDEX_DRY_RUN:
            sent_today = count_yandex_replies_today()


_stop = {"event": None}


def stop_event_set() -> bool:
    event = _stop["event"]
    return bool(event and event.is_set())


async def _handle_order(session: BrowserSession, order: dict):
    print(f"👁️ {order['title']}")
    if not order["url"]:
        print("   Нет ссылки на заказ")
        add_yandex_order(order["id"], order["title"], "", "no_url")
        return

    page = await session.new_page()
    try:
        await page.goto(order["url"], wait_until="domcontentloaded", timeout=60000)
        description = await read_order_text(page)
        if not description:
            print("   Пустая карточка")
            return

        if reason := reject_reason(description):
            print(f"   ⏩ Мимо [{reason}]")
            add_yandex_order(order["id"], order["title"], order["url"], "rejected")
            return

        if not await is_order_suitable(order["title"], description):
            add_yandex_order(order["id"], order["title"], order["url"], "rejected_ai")
            return

        reply = sanitize_reply(await generate_reply(order["title"], description))
        sent, _note = await send_reply(page, reply, description)
        if sent:
            add_yandex_order(order["id"], order["title"], order["url"], "replied", reply)
            await notify(f"✅ Яндекс отклик: {order['title']}\n{order['url']}\n\n{reply}")
        elif YANDEX_DRY_RUN:
            print(f"✨ Подходит, черновик готов: {order['title']}")
    except Exception as e:
        print(f"Ошибка [{order['title']}]: {e}")
    finally:
        await page.close()


def setup_signals(stop_event: asyncio.Event):
    loop = asyncio.get_running_loop()
    hits = {"n": 0}

    def on_stop():
        hits["n"] += 1
        if hits["n"] >= 2:
            print("\n💥 Принудительный выход.")
            os._exit(1)
        print("\n⏹ Ctrl+C — останавливаем... (ещё раз = жёстко)")
        stop_event.set()
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, on_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: on_stop())


async def main():
    init_yandex_db()
    print("Яндекс Исполнители.")
    if YANDEX_DRY_RUN:
        print("Режим проверки: отклики не отправляются. Боевой режим: YANDEX_DRY_RUN=false")
    await check_ollama()

    stop_event = asyncio.Event()
    _stop["event"] = stop_event
    setup_signals(stop_event)
    await run(stop_event)
    print("Остановка.")
