import aiosqlite
import os
from datetime import datetime

DATA_DIR = os.getenv('DATA_DIR', '.')
DB_PATH  = os.path.join(DATA_DIR, 'leads.db')

_db: aiosqlite.Connection | None = None


async def initialize():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute('''CREATE TABLE IF NOT EXISTS seen (
        username TEXT PRIMARY KEY,
        added_at TEXT DEFAULT (datetime('now'))
    )''')
    await _db.execute('''CREATE TABLE IF NOT EXISTS queue (
        username TEXT PRIMARY KEY,
        query    TEXT,
        added_at TEXT DEFAULT (datetime('now')),
        checked  INTEGER DEFAULT 0
    )''')
    await _db.execute('''CREATE TABLE IF NOT EXISTS leads (
        username    TEXT PRIMARY KEY,
        niche       TEXT,
        subscribers INTEGER,
        last_post   TEXT,
        message     TEXT,
        found_at    TEXT DEFAULT (datetime('now')),
        outcome     TEXT DEFAULT 'new'
    )''')
    await _db.commit()


async def is_seen(username: str) -> bool:
    cur = await _db.execute('SELECT 1 FROM seen WHERE username=?', (username,))
    return await cur.fetchone() is not None


async def mark_seen(username: str):
    await _db.execute('INSERT OR IGNORE INTO seen(username) VALUES(?)', (username,))
    await _db.commit()


async def queue_for_check(username: str, query: str):
    await _db.execute(
        'INSERT OR IGNORE INTO queue(username, query) VALUES(?,?)', (username, query)
    )
    await _db.commit()


async def get_next_from_queue() -> tuple[str, str] | None:
    cur = await _db.execute(
        'SELECT username, query FROM queue WHERE checked=0 ORDER BY added_at LIMIT 1'
    )
    row = await cur.fetchone()
    return (row['username'], row['query']) if row else None


async def mark_checked(username: str):
    await _db.execute('UPDATE queue SET checked=1 WHERE username=?', (username,))
    await _db.commit()


async def save_lead(username: str, niche: str, subscribers: int, last_post: str, message: str):
    await _db.execute(
        'INSERT OR IGNORE INTO leads(username, niche, subscribers, last_post, message) '
        'VALUES(?,?,?,?,?)',
        (username, niche, subscribers, last_post, message)
    )
    await _db.commit()


async def update_lead_outcome(username: str, outcome: str):
    await _db.execute('UPDATE leads SET outcome=? WHERE username=?', (outcome, username))
    await _db.commit()


async def queue_size() -> int:
    cur = await _db.execute('SELECT COUNT(*) FROM queue WHERE checked=0')
    row = await cur.fetchone()
    return row[0]


async def get_stats() -> dict:
    today = datetime.now().strftime('%Y-%m-%d')
    results = {}
    for key, sql, params in [
        ('total',   'SELECT COUNT(*) FROM leads', ()),
        ('today',   "SELECT COUNT(*) FROM leads WHERE found_at LIKE ?", (f'{today}%',)),
        ('wrote',   "SELECT COUNT(*) FROM leads WHERE outcome='wrote'", ()),
        ('skipped', "SELECT COUNT(*) FROM leads WHERE outcome='skipped'", ()),
        ('queue',   'SELECT COUNT(*) FROM queue WHERE checked=0', ()),
    ]:
        cur = await _db.execute(sql, params)
        row = await cur.fetchone()
        results[key] = row[0]
    return results
