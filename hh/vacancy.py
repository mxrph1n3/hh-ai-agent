import asyncio
from playwright.async_api import Page
from ai.analyzer import is_vacancy_suitable
from filters.title import title_passes, reject_reason
from hh.apply import Applicant
from hh.captcha import solve_captcha
from storage.db import is_job_applied, add_applied_job


async def process_vacancy(
    session,
    title: str,
    href: str,
    notify,
) -> None:
    """Открывает вакансию, фильтрует, откликается."""
    job_id = href.split("vacancy/")[1].split("?")[0] if "vacancy/" in href else None
    if not job_id or is_job_applied(job_id):
        return

    if reason := reject_reason(title):
        print(f"⏩ Мусор [{reason}]: {title}")
        add_applied_job(job_id, title, href, "rejected")
        return
    if not title_passes(title):
        print(f"⏩ Не маркетинг: {title}")
        add_applied_job(job_id, title, href, "rejected")
        return

    print(f"👁️ {title}")
    page = await session.new_page()
    applicant = Applicant()

    try:
        await page.goto(href, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        desc_loc = page.locator('div[data-qa="vacancy-description"]').first
        while not await desc_loc.is_visible():
            print(f"⚠️ Капча или нет описания: {title}")
            if not await solve_captcha(page, title, notify):
                break

        if not await desc_loc.is_visible():
            return

        description = await desc_loc.inner_text()
        if await is_vacancy_suitable(title, description):
            print(f"✨ Подходит: {title}")
            await applicant.apply(page, title, href, job_id, description, notify)
        else:
            print(f"❌ ИИ отклонил: {title}")
            add_applied_job(job_id, title, href, "rejected_ai")
    except Exception as e:
        print(f"Ошибка [{title}]: {e}")
    finally:
        await page.close()
