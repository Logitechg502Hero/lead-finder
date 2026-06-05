from database import get_stats

_notified = 0
_wrote    = 0


async def increment_notified():
    global _notified
    _notified += 1


async def increment_wrote():
    global _wrote
    _wrote += 1


async def summary() -> str:
    s = await get_stats()
    return (
        f'📊 *Статистика лидгена*\n\n'
        f'Всего лидов найдено: {s["total"]}\n'
        f'За сегодня: {s["today"]}\n'
        f'Написал: {s["wrote"]}\n'
        f'Пропустил: {s["skipped"]}\n'
        f'В очереди на проверку: {s["queue"]}\n\n'
        f'_За эту сессию: уведомлений {_notified}, написал {_wrote}_'
    )
