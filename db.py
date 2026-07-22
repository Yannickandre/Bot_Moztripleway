import os
import aiosqlite
from typing import List, Optional

DB_PATH = os.getenv("SQLITE_PATH", "bot.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocked (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                by_admin INTEGER,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duplicates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                info TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                by_admin INTEGER,
                created_at TEXT
            )
        """)
        await db.commit()

# Users
async def add_or_update_user(user) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users(id, username, first_name) VALUES(?, ?, ?)",
            (user.id, user.username, user.first_name)
        )
        await db.commit()

async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(1) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

async def get_users_list() -> List[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, username, first_name FROM users ORDER BY id") as cur:
            return await cur.fetchall()

# Blocked
async def block_user(user_id: int, reason: str, by_admin: Optional[int] = None) -> None:
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO blocked(user_id, reason, by_admin, created_at) VALUES(?, ?, ?, ?)",
            (user_id, reason, by_admin, now)
        )
        await db.execute(
            "INSERT INTO history(user_id, action, details, by_admin, created_at) VALUES(?, 'block', ?, ?, ?)",
            (user_id, reason, by_admin, now)
        )
        await db.commit()

async def unblock_user(user_id: int, by_admin: Optional[int] = None) -> None:
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM blocked WHERE user_id = ?", (user_id,))
        await db.execute(
            "INSERT INTO history(user_id, action, details, by_admin, created_at) VALUES(?, 'unblock', '', ?, ?)",
            (user_id, by_admin, now)
        )
        await db.commit()

async def is_blocked(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM blocked WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return bool(row)

async def get_blocked() -> List[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, reason, by_admin, created_at FROM blocked ORDER BY created_at DESC") as cur:
            return await cur.fetchall()

# Duplicates
async def add_duplicate(user_id: Optional[int], info: str) -> None:
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO duplicates(user_id, info, created_at) VALUES(?, ?, ?)", (user_id, info, now))
        await db.commit()

async def get_duplicates() -> List[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, user_id, info, created_at FROM duplicates ORDER BY created_at DESC") as cur:
            return await cur.fetchall()

# History
async def add_history(user_id: int, action: str, details: str, by_admin: Optional[int] = None) -> None:
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO history(user_id, action, details, by_admin, created_at) VALUES(?, ?, ?, ?, ?)",
            (user_id, action, details, by_admin, now)
        )
        await db.commit()

async def get_history(user_id: int) -> List[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, action, details, by_admin, created_at FROM history WHERE user_id = ? ORDER BY created_at DESC", (user_id,)) as cur:
            return await cur.fetchall()
