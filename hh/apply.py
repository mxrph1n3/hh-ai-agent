import asyncio
import random
import re
import html
from playwright.async_api import Page
from config import TARGET_RESUME_NAME
from ai.analyzer import generate_cover_letter
from storage.db import add_applied_job


class Applicant:
    """Отклик на вакансию: с письмом или без."""

    async def apply(
        self,
        page: Page,
        title: str,
        href: str,
        job_id: str,
        description: str,
        notify,
    ) -> bool:
        apply_btn = page.locator(
            'a[data-qa="vacancy-response-link-top"], '
            'button[data-qa="vacancy-response-link-top"], '
            '[data-qa="vacancy-response-link-top"]'
        ).first

        if not await apply_btn.count() or not await apply_btn.is_visible():
            apply_btn = page.get_by_role("link", name=re.compile("откликнуться", re.I)).first
            if not await apply_btn.count():
                apply_btn = page.get_by_role("button", name=re.compile("откликнуться", re.I)).first

        if not await apply_btn.count() or not await apply_btn.is_visible():
            if await self._already_applied(page):
                add_applied_job(job_id, title, href, "already_applied")
                print(f"ℹ️ Уже откликались: {title}")
                return False
            print(f"Кнопка отклика не найдена: {title}")
            add_applied_job(job_id, title, href, "no_button")
            return False

        await page.mouse.move(random.randint(100, 700), random.randint(100, 500))
        await page.mouse.wheel(0, random.randint(200, 600))
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await apply_btn.click()
        await asyncio.sleep(2.5)

        if await self._already_applied(page):
            add_applied_job(job_id, title, href)
            await notify(f"✅ Отклик (одним кликом): {title}\n{href}")
            print(f"✅ Отклик отправлен (одним кликом): {title}")
            return True

        await self._select_resume(page)
        await self._dismiss_questions(page)

        letter_sent = False
        cover_letter = ""
        has_letter = await self._has_letter_ui(page)

        if has_letter:
            cover_letter = await generate_cover_letter(title, description)
            letter_sent = await self._fill_letter(page, cover_letter)
            if not letter_sent:
                print(f"ℹ️ Письмо недоступно — отклик без письма: {title}")
        else:
            print(f"ℹ️ Сопроводительное не требуется: {title}")

        success = False
        for _ in range(3):
            if await self._click_submit(page):
                success = True
            await asyncio.sleep(1.2)
            await self._dismiss_questions(page)
            if await self._already_applied(page):
                success = True
            if success:
                break
            await asyncio.sleep(1)

        if not success:
            print(f"❌ Не удалось подтвердить отклик: {title}")
            try:
                await page.screenshot(path="apply_fail.png")
                print("   Скриншот: apply_fail.png")
            except Exception:
                pass
            return False

        add_applied_job(job_id, title, href)
        if letter_sent and cover_letter:
            safe = html.escape(cover_letter)
            await notify(f"✅ Отклик: {title}\n{href}\n\nПисьмо:\n{safe}")
            print(f"✅ Отклик с письмом: {title}")
        else:
            await notify(f"✅ Отклик без письма: {title}\n{href}")
            print(f"✅ Отклик без письма: {title}")
        return True

    async def _already_applied(self, page: Page) -> bool:
        for sel in (
            'text="Вы откликнулись"', 'text="Отклик отправлен"',
            '[data-qa="vacancy-response-link-view-topic"]',
            'a:has-text("Перейти в чат")', 'button:has-text("Перейти в чат")',
        ):
            loc = page.locator(sel).first
            try:
                if await loc.count() and await loc.is_visible():
                    return True
            except Exception:
                pass
        apply = page.locator('[data-qa="vacancy-response-link-top"]').first
        try:
            if await apply.count() == 0:
                return True
            if await apply.is_visible():
                txt = (await apply.inner_text()).lower().replace("ё", "е")
                if "откликнуться" not in txt and "отклик" in txt:
                    return True
        except Exception:
            pass
        return False

    async def _select_resume(self, page: Page):
        if not TARGET_RESUME_NAME:
            return
        try:
            dropdown = page.locator(
                '[data-qa*="resume-select"], [data-qa*="resume-selector"], '
                '[data-qa="vacancy-response-resume-selector"]'
            ).first
            if await dropdown.count() and await dropdown.is_visible():
                await dropdown.click()
                await asyncio.sleep(0.8)
                target = page.locator(f'text="{TARGET_RESUME_NAME}"').first
                if await target.count() and await target.is_visible():
                    await target.click()
                    await asyncio.sleep(0.8)
        except Exception as e:
            print(f"⚠️ Выбор резюме: {e}")

    async def _has_letter_ui(self, page: Page) -> bool:
        for sel in (
            'textarea', '[data-qa*="letter"]', 'text="сопроводительное"',
            'text="Написать сопроводительное"', '[data-qa*="letter-toggle"]',
        ):
            loc = page.locator(sel).first
            try:
                if await loc.count() and await loc.is_visible():
                    return True
            except Exception:
                pass
        return False

    async def _fill_letter(self, page: Page, text: str) -> bool:
        for sel in (
            '[data-qa*="letter-toggle"]', 'text="Написать сопроводительное"',
            'text="Добавить сопроводительное"',
        ):
            toggle = page.locator(sel).first
            try:
                if await toggle.count() and await toggle.is_visible():
                    await toggle.click()
                    await asyncio.sleep(0.8)
                    break
            except Exception:
                pass
        for sel in ('textarea[data-qa*="letter"]', 'textarea'):
            area = page.locator(sel).first
            try:
                await area.wait_for(state="visible", timeout=1500)
                await area.fill(text)
                return True
            except Exception:
                continue
        return False

    async def _click_submit(self, page: Page) -> bool:
        for sel in (
            'button[data-qa="vacancy-response-submit-popup"]',
            'button[data-qa="vacancy-response-letter-submit"]',
            'button[data-qa*="vacancy-response-submit"]',
            'button:has-text("Отправить отклик")',
            'button:has-text("Откликнуться")',
            'button:has-text("Продолжить")',
        ):
            btn = page.locator(sel).first
            try:
                if await btn.count() == 0:
                    continue
                await btn.wait_for(state="visible", timeout=2000)
                await btn.click(timeout=3000)
                await asyncio.sleep(2)
                return True
            except Exception:
                try:
                    if await btn.count():
                        await btn.evaluate("el => el.click()")
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue
        return False

    async def _dismiss_questions(self, page: Page):
        for sel in (
            'button:has-text("Продолжить")', 'button:has-text("Откликнуться")',
            'button:has-text("Готово")', 'button[data-qa*="submit"]',
        ):
            btn = page.locator(sel).first
            try:
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass
