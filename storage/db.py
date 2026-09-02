import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent.db")


def _connect():
    return sqlite3.connect(DB_PATH)


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
