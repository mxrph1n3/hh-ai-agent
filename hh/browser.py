import os
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth
from config import HEADLESS, BROWSER_PROXY

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "state.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)


class BrowserSession:
    """Управление Playwright-браузером и сессией HH."""

    def __init__(self):
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self):
        self.playwright = await async_playwright().start()

        env = os.environ.copy()
        for key in _PROXY_ENV_KEYS:
            env.pop(key, None)

        launch_kwargs = {
            "headless": HEADLESS,
            "env": env,
        }
        if BROWSER_PROXY:
            print(f"Браузер: прокси {BROWSER_PROXY}")
            launch_kwargs["proxy"] = {"server": BROWSER_PROXY}
        else:
            # Игнор битого системного прокси (ERR_PROXY_CONNECTION_FAILED)
            launch_kwargs["args"] = ["--no-proxy-server"]
            print("Браузер: без прокси (системный игнорируется)")

        self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        kwargs = {"user_agent": USER_AGENT}
        if os.path.exists(STATE_FILE):
            kwargs["storage_state"] = STATE_FILE
        self.context = await self.browser.new_context(**kwargs)
        self.page = await self.context.new_page()
        await Stealth().apply_stealth_async(self.page)

    async def new_page(self) -> Page:
        page = await self.context.new_page()
        await Stealth().apply_stealth_async(page)
        return page

    async def save_session(self):
        await self.context.storage_state(path=STATE_FILE)

    async def stop(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            try:
                if self.browser and self.browser.process:
                    self.browser.process.kill()
            except Exception:
                pass
        self.page = self.context = self.browser = self.playwright = None
