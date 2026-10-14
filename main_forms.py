import asyncio
import os

from agent.notify import notify
from agent.runner import setup_signals
from ai.analyzer import check_ollama
from hh.chats import fill_chat_forms
from hh.client import HHAgent
from storage.db import init_db


async def main():
    init_db()
    print("Только анкеты из чатов. Поиск вакансий не запускается.")
    await check_ollama()

    stop_event = asyncio.Event()
    setup_signals(stop_event)
    agent = HHAgent()
    try:
        await agent.start()
        if not await agent.login():
            print("Вход в HH не выполнен.")
            return
        await fill_chat_forms(agent.session, notify)
        print("Проход по чатам закончен.")
        print("Окна анкет не закрываю. Перечитайте и отправьте сами.")
        print("Ctrl+C закроет браузер.")
        await stop_event.wait()
    finally:
        print("Закрываем браузер...")
        await agent.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановка.")
        os._exit(0)
