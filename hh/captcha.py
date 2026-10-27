import asyncio
import random
from playwright.async_api import Page


async def solve_captcha(page: Page, title: str, notify) -> bool:
    """Решает капчу через консоль. True = описание появилось."""
    await page.screenshot(path="captcha.png")
    print(f"🚨 Капча: {title}. Картинка: captcha.png")
    solution = await asyncio.to_thread(input, "👉 Текст капчи: ")

    print(f"Вводим: {solution}")
    input_field = page.locator('input[type="text"]').first
    if await input_field.is_visible():
        await input_field.click()
        await asyncio.sleep(random.uniform(0.5, 1.2))
        for char in solution:
            if char == " ":
                await asyncio.sleep(random.uniform(0.6, 1.5))
            await input_field.type(char, delay=random.randint(150, 400))
        await asyncio.sleep(random.uniform(1.0, 2.5))
        await input_field.press("Enter")
        await asyncio.sleep(5)
    else:
        print("Поле капчи не найдено — обновляем страницу...")
        await page.reload()
        await asyncio.sleep(4)

    desc = page.locator('div[data-qa="vacancy-description"]').first
    if await desc.is_visible():
        print("✅ Капча пройдена.")
        return True

    print("❌ Капча не пройдена.")
    return False
