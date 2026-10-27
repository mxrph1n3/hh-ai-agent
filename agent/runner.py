import asyncio
import os
import signal
from config import (
    ENABLE_AI_FILTER, LOOP_INTERVAL_MINUTES, ENABLE_CHATS, ENABLE_FORMS,
)
from storage.db import init_db
from hh.client import HHAgent
from agent.notify import notify
from ai.analyzer import check_ollama


async def run_agent(stop_event: asyncio.Event):
    agent = HHAgent()
    try:
        try:
            await agent.start()
        except Exception as e:
            print(f"❌ Не удалось запустить браузер: {e}")
            stop_event.set()
            return

        try:
            logged_in = await agent.login()
        except Exception as e:
            print(f"❌ Ошибка входа: {e}")
            stop_event.set()
            return

        if not logged_in:
            print("❌ Вход в HH не выполнен — останавливаем.")
            stop_event.set()
            return

        await notify("агент запущен. режим: удаленка по всему миру.")

        while not stop_event.is_set():
            stages = [("поиск", lambda: agent.run_search_cycle(notify))]
            if ENABLE_CHATS:
                stages.append(("чаты", lambda: agent.check_chats(notify)))
            if ENABLE_FORMS:
                stages.append(("анкеты", lambda: agent.process_forms(notify)))
            for name, stage in stages:
                if stop_event.is_set():
                    break
                try:
                    await stage()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"Ошибка цикла ({name}): {e}")

            print(f"Ожидание {LOOP_INTERVAL_MINUTES} мин...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=LOOP_INTERVAL_MINUTES * 60)
            except asyncio.TimeoutError:
                pass
    finally:
        print("Закрываем браузер...")
        await agent.stop()


def setup_signals(stop_event: asyncio.Event):
    loop = asyncio.get_running_loop()
    sigint_count = {"n": 0}

    def on_stop():
        sigint_count["n"] += 1
        if sigint_count["n"] >= 2:
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
    init_db()
    print("Инициализация завершена.")
    if ENABLE_AI_FILTER:
        await check_ollama()

    stop_event = asyncio.Event()
    setup_signals(stop_event)

    tasks = [asyncio.create_task(run_agent(stop_event), name="agent")]

    stop_waiter = asyncio.create_task(stop_event.wait())
    await asyncio.wait({*tasks, stop_waiter}, return_when=asyncio.FIRST_COMPLETED)

    stop_event.set()

    for t in (*tasks, stop_waiter):
        if not t.done():
            t.cancel()

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, stop_waiter, return_exceptions=True),
            timeout=5,
        )
    except asyncio.TimeoutError:
        os._exit(1)

    print("Остановка.")
