import asyncio
from config import SEARCH_QUERIES, HH_SEARCH_EXTRA, SEARCH_CONFIGS
from hh.browser import BrowserSession
from hh.auth import ensure_logged_in
from hh.search import build_search_url, collect_vacancy_links, has_next_page, go_next_page
from hh.vacancy import process_vacancy
from hh.chats import check_new_messages


class HHAgent:
    """Оркестратор: поиск → фильтр → отклик."""

    def __init__(self):
        self.session = BrowserSession()

    async def start(self):
        await self.session.start()

    async def stop(self):
        await self.session.stop()

    async def login(self) -> bool:
        return await ensure_logged_in(self.session)

    async def run_search_cycle(self, notify):
        print("Начинаем поиск вакансий...")
        page = self.session.page

        for query in SEARCH_QUERIES:
            print(f"\n{'=' * 38}\n🔍 {query}\n{'=' * 38}")

            for cfg in SEARCH_CONFIGS:
                print(f"📍 {cfg['name']}")
                url = build_search_url(query, HH_SEARCH_EXTRA, cfg["params"])
                print(f"🔗 {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                page_num = 1
                while True:
                    print(f"📄 Страница {page_num}...")
                    links = await collect_vacancy_links(page)
                    print(f"   Найдено: {len(links)}")

                    if not links and page_num == 1:
                        await asyncio.sleep(3)
                        links = await collect_vacancy_links(page)
                        print(f"   Повтор: {len(links)}")
                        if not links:
                            await page.screenshot(path="search_empty.png")
                            print("   Скрин: search_empty.png")

                    for title, href in links:
                        await process_vacancy(self.session, title, href, notify)

                    if await has_next_page(page):
                        print("➡️ Следующая страница...")
                        await go_next_page(page)
                        page_num += 1
                    else:
                        print("🛑 Конец выдачи.")
                        break

    async def check_chats(self, notify):
        await check_new_messages(self.session, notify)
