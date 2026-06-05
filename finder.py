"""Ищет Telegram-каналы на tgstat.ru по запросам."""

import aiohttp
import asyncio
import ssl
import certifi
import re
import logging
from datetime import datetime

import database

log = logging.getLogger(__name__)

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://tgstat.ru/',
}

SEARCH_QUERIES = [
    'барбершоп', 'барбер', 'фитнес тренер', 'психолог',
    'коуч', 'репетитор', 'салон красоты', 'стоматолог',
    'маникюр', 'массаж', 'юрист', 'бухгалтер', 'фотограф',
    'флорист', 'кондитер', 'дизайнер интерьера', 'риэлтор',
    'нутрициолог', 'логопед', 'детский психолог', 'визажист',
]

NIGHT_START = 0
NIGHT_END   = 8


def _is_night() -> bool:
    return NIGHT_START <= datetime.now().hour < NIGHT_END


def _sleep(base: float) -> float:
    return base * 2 if _is_night() else base


def make_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CTX))


async def parse_tgstat(query: str, page: int) -> list[str]:
    url = f'https://tgstat.ru/ru/search?q={query}&peer_type=channel&page={page}'
    try:
        async with make_session() as s:
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                html = await r.text(errors='replace')
    except Exception as e:
        log.warning(f'tgstat [{query} p{page}]: {e}')
        return []

    # Извлекаем usernames из ссылок вида /channel/@username или t.me/username
    usernames = set()
    for pattern in [
        r'/channel/@([\w_]{3,32})',
        r't\.me/([\w_]{3,32})',
        r'peer=([\w_]{3,32})',
    ]:
        for m in re.finditer(pattern, html):
            u = m.group(1).lower()
            if u not in ('search', 'ru', 'en', 'api', 'login'):
                usernames.add(u)

    return list(usernames)


async def finder_loop(notify_queue: asyncio.Queue):
    log.info('finder_loop started')
    while True:
        for query in SEARCH_QUERIES:
            for page in range(1, 10):
                usernames = await parse_tgstat(query, page)
                new_count = 0
                for username in usernames:
                    if not await database.is_seen(username):
                        await database.queue_for_check(username, query)
                        new_count += 1
                if new_count:
                    log.info(f'[finder] {query} p{page}: +{new_count} в очередь')
                if not usernames:
                    break  # нет больше страниц
                await asyncio.sleep(_sleep(3))
            await asyncio.sleep(_sleep(10))
