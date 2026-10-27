import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent.db")

# Статусы формы:
# new → filled (заполнена, ждёт вас) → submitted (вы отправили сами)
# needs_input — не хватает фактов для обязательных полей
# manual — нужен человек (вход в Google, капча, файл, не распознали)
# skipped / failed / not_form
FORM_STATUSES = (
    "new", "filled", "submitted", "needs_input",
    "manual", "skipped", "failed", "not_form",
)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applied_jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                msg_id TEXT PRIMARY KEY,
                chat_id TEXT,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                last_preview TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                kind TEXT,
                chat_id TEXT,
                message_id TEXT,
                vacancy_title TEXT,
                company TEXT,
                vacancy_url TEXT,
                context TEXT,
                status TEXT DEFAULT 'new',
                answers_json TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def is_job_applied(job_id: str) -> bool:
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM applied_jobs WHERE id = ?", (job_id,)
        ).fetchone() is not None


def add_applied_job(job_id: str, title: str, url: str, status: str = "applied"):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO applied_jobs (id, title, url) VALUES (?, ?, ?)",
            (job_id, title, url),
        )


def is_message_processed(msg_id: str) -> bool:
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM chat_messages WHERE msg_id = ?", (msg_id,)
        ).fetchone() is not None


def add_processed_message(msg_id: str, chat_id: str, text: str):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_messages (msg_id, chat_id, text) VALUES (?, ?, ?)",
            (msg_id, chat_id, text),
        )


def has_any_chats() -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM chats LIMIT 1").fetchone() is not None


def get_chat_preview(chat_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_preview FROM chats WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["last_preview"] if row else None


def save_chat(chat_id: str, title: str, company: str, last_preview: str):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO chats (chat_id, title, company, last_preview) VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 title = excluded.title, company = excluded.company,
                 last_preview = excluded.last_preview, updated_at = CURRENT_TIMESTAMP""",
            (chat_id, title, company, last_preview),
        )


def add_form(url: str, kind: str, chat_id: str, message_id: str, vacancy_title: str,
             company: str, vacancy_url: str, context: str) -> int | None:
    """Добавляет ссылку в очередь. None — такая ссылка уже есть."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO forms
               (url, kind, chat_id, message_id, vacancy_title, company, vacancy_url, context)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, kind, chat_id, message_id, vacancy_title, company, vacancy_url, context),
        )
        return cur.lastrowid if cur.rowcount else None


def get_form(form_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM forms WHERE id = ?", (form_id,)).fetchone()
        return _form_row(row) if row else None


def get_forms_by_status(status: str, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM forms WHERE status = ? ORDER BY id LIMIT ?", (status, limit)
        ).fetchall()
        return [_form_row(r) for r in rows]


def update_form(form_id: int, status: str | None = None, answers: list | None = None,
                note: str | None = None):
    sets, args = ["updated_at = CURRENT_TIMESTAMP"], []
    if status is not None:
        assert status in FORM_STATUSES, status
        sets.append("status = ?")
        args.append(status)
    if answers is not None:
        sets.append("answers_json = ?")
        args.append(json.dumps(answers, ensure_ascii=False))
    if note is not None:
        sets.append("note = ?")
        args.append(note)
    with _connect() as conn:
        conn.execute(f"UPDATE forms SET {', '.join(sets)} WHERE id = ?", (*args, form_id))


def _form_row(row: sqlite3.Row) -> dict:
    form = dict(row)
    form["answers"] = json.loads(form.pop("answers_json") or "[]")
    return form
