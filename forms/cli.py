"""Просмотр анкет, которые заполнил агент. Сам агент ничего не отправляет.

python -m forms.cli list                      # все анкеты
python -m forms.cli show <id>                 # ответы и скриншоты
python -m forms.cli fix <id> <номер> <текст>  # поправить ответ (галочки через «;», «-» — очистить)
python -m forms.cli open <id>                 # открыть в браузере уже заполненной — проверить и отправить самому
python -m forms.cli done <id>                 # отметить, что отправили
python -m forms.cli skip <id>                 # не отправлять
python -m forms.cli refill <id>               # заполнить заново с нуля в следующем цикле агента
"""
import asyncio
import glob
import os
import sys
from config import FORMS_SHOTS_DIR
from forms.review import build_review_text, apply_fix, has_missing_required
from storage.db import init_db, get_form, get_forms_by_status, update_form

LIST_ORDER = ("filled", "needs_input", "manual", "new", "failed", "submitted", "skipped")


def main(argv: list[str]):
    init_db()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        for status in LIST_ORDER:
            for f in get_forms_by_status(status, 500):
                print(f"#{f['id']:<4} {status:<12} {f['vacancy_title'] or '?'} ({f['company'] or '?'}) {f['url']}")
        return
    if cmd not in ("show", "fix", "open", "done", "skip", "refill") or len(argv) < 2:
        print(__doc__)
        return

    form = get_form(int(argv[1]))
    if not form:
        print("Анкета не найдена")
        return

    if cmd == "show":
        print(build_review_text(form))
        shots = sorted(glob.glob(os.path.join(FORMS_SHOTS_DIR, f"form{form['id']}_*.png")))
        if shots:
            print("\nСкриншоты:\n" + "\n".join(shots))
    elif cmd == "fix":
        if len(argv) < 4:
            print("Формат: fix <id> <номер поля> <текст>")
            return
        answers, error = apply_fix(form, int(argv[2]), " ".join(argv[3:]))
        if error:
            print(error)
            return
        status = form["status"]
        if status == "needs_input" and not has_missing_required(answers):
            status = "filled"
        update_form(form["id"], status=status, answers=answers)
        print(f"Сохранено. Статус: {status}")
    elif cmd == "open":
        asyncio.run(_open(form))
    elif cmd == "done":
        update_form(form["id"], status="submitted")
        print("Отмечено как отправленная.")
    elif cmd == "skip":
        update_form(form["id"], status="skipped")
        print("Пропущено.")
    elif cmd == "refill":
        update_form(form["id"], status="new", answers=[], note="")
        print("Агент заполнит анкету заново в следующем цикле.")


async def _open(form: dict):
    """Видимый браузер: вписывает сохранённые ответы и оставляет форму вам."""
    from playwright.async_api import async_playwright
    from forms.runner import run_form

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--no-proxy-server"])
        page = await browser.new_page(viewport=None)
        print("Заполняю сохранёнными ответами...")
        res = await run_form(page, form)
        if res["answers"]:
            update_form(form["id"], answers=res["answers"])
        print(f"Готово: {res['status']} {res['note']}".strip())
        print("Проверьте форму в браузере и отправьте её сами.")
        answer = await asyncio.to_thread(input, "Отправили? [y — отметить отправленной / Enter — закрыть]: ")
        if answer.strip().lower() in ("y", "д", "да", "yes"):
            update_form(form["id"], status="submitted")
            print("Отмечено как отправленная.")
        await browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
