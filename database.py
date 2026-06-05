import aiosqlite
import os
from datetime import datetime

DATA_DIR = os.getenv('DATA_DIR', '.')
DB_PATH  = os.path.join(DATA_DIR, 'leads.db')


async def initialize():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript('''
            CREATE TABLE IF NOT EXISTS seen (
                username TEXT PRIMARY KEY,
                added_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS queue (
                username TEXT PRIMARY KEY,
                query    TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                checked  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS leads (
                username    TEXT PRIMARY KEY,
                niche       TEXT,
                subscribers INTEGER,
                last_post   TEXT,
                message     TEXT,
                found_at    TEXT DEFAULT (datetime('now')),
                outcome     TEXT DEFAULT 'new'
            );
        ''')
        await db.commit()


async def is_seen(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute('SELECT 1 FROM seen WHERE username=?', (username,))
        return await cur.fetchone() is not None


async def mark_seen(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO seen(username) VALUES(?)', (username,))
        await db.commit()


async def queue_for_check(username: str, query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO queue(username, query) VALUES(?,?)', (username, query)
        )
        await db.commit()


async def get_next_from_queue() -> tuple[str, str] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            'SELECT username, query FROM queue WHERE checked=0 ORDER BY added_at LIMIT 1'
        )
        row = await cur.fetchone()
        return (row[0], row[1]) if row else None


async def mark_checked(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE queue SET checked=1 WHERE username=?', (username,))
        await db.commit()


async def save_lead(username: str, niche: str, subscribers: int, last_post: str, message: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO leads(username, niche, subscribers, last_post, message) '
            'VALUES(?,?,?,?,?)',
            (username, niche, subscribers, last_post, message)
        )
        await db.commit()


async def update_lead_outcome(username: str, outcome: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE leads SET outcome=? WHERE username=?', (outcome, username))
        await db.commit()


async def queue_size() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute('SELECT COUNT(*) FROM queue WHERE checked=0')
        row = await cur.fetchone()
        return row[0]


async def get_stats() -> dict:
    today = datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        total_cur  = await db.execute('SELECT COUNT(*) FROM leads')
        today_cur  = await db.execute("SELECT COUNT(*) FROM leads WHERE found_at LIKE ?", (f'{today}%',))
        wrote_cur  = await db.execute("SELECT COUNT(*) FROM leads WHERE outcome='wrote'")
        skip_cur   = await db.execute("SELECT COUNT(*) FROM leads WHERE outcome='skipped'")
        queue_cur  = await db.execute('SELECT COUNT(*) FROM queue WHERE checked=0')
        total  = (await total_cur.fetchone())[0]
        today_ = (await today_cur.fetchone())[0]
        wrote  = (await wrote_cur.fetchone())[0]
        skip   = (await skip_cur.fetchone())[0]
        queue  = (await queue_cur.fetchone())[0]
    return {'total': total, 'today': today_, 'wrote': wrote, 'skipped': skip, 'queue': queue}
