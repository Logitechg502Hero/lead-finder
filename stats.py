import aiosqlite
import os
from datetime import datetime

DATA_DIR = os.getenv('DATA_DIR', '.')
DB_PATH  = os.path.join(DATA_DIR, 'leads.db')

# In-memory счётчики сессии
_notified = 0
_wrote    = 0


async def increment_notified():
    global _notified
    _notified += 1


async def increment_wrote():
    global _wrote
    _wrote += 1


async def summary() -> str:
    s = await database_stats()
    return (
        f'📊 *Статистика лидгена*\n\n'
        f'Всего лидов найдено: {s["total"]}\n'
        f'За сегодня: {s["today"]}\n'
        f'Написал: {s["wrote"]}\n'
        f'Пропустил: {s["skipped"]}\n'
        f'В очереди на проверку: {s["queue"]}\n\n'
        f'_За эту сессию: уведомлений {_notified}, написал {_wrote}_'
    )


async def database_stats() -> dict:
    today = datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        rows = {}
        for key, sql, params in [
            ('total',   'SELECT COUNT(*) FROM leads', ()),
            ('today',   "SELECT COUNT(*) FROM leads WHERE found_at LIKE ?", (f'{today}%',)),
            ('wrote',   "SELECT COUNT(*) FROM leads WHERE outcome='wrote'", ()),
            ('skipped', "SELECT COUNT(*) FROM leads WHERE outcome='skipped'", ()),
            ('queue',   'SELECT COUNT(*) FROM queue WHERE checked=0', ()),
        ]:
            cur = await db.execute(sql, params)
            rows[key] = (await cur.fetchone())[0]
    return rows
