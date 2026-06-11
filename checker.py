"""Проверяет найденные каналы: подписчики, активность, наличие бота."""

import aiohttp
import asyncio
import ssl
import certifi
import re
import logging
from datetime import datetime, timezone

import database
import notifier
from templates import detect_niche, build_message

log = logging.getLogger(__name__)

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

MIN_SUBSCRIBERS = 200
MAX_SUBSCRIBERS = 50_000
MAX_POST_AGE_DAYS = 14

# Сигналы ищем ТОЛЬКО в bio/описании, не во всём HTML
# (в HTML t.me всегда есть margin-bottom, font-roboto и т.п. → ложное 'bot')
BOT_SIGNALS_RE = re.compile(
    r'(@\w*bot\b|\bбот\b|онлайн[- ]запись|запись через бот|/start|t\.me/\w+bot)',
    re.IGNORECASE
)

NIGHT_START = 0
NIGHT_END   = 8


def _is_night() -> bool:
    return NIGHT_START <= datetime.now().hour < NIGHT_END


def make_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CTX))


def _parse_subscribers(html: str) -> int:
    # <span class="counter_value">82K</span> <span class="counter_type">subscribers</span>
    m = re.search(
        r'counter_value">([^<]+)</span>\s*<span class="counter_type">\s*(?:subscriber|подписчик)',
        html, re.IGNORECASE
    )
    if not m:
        # запасной вариант: «1 234 subscribers» прямым текстом
        m = re.search(r'([\d.,\sKMkmкКмМ]+?)\s*(?:subscriber|подписчик)', html, re.IGNORECASE)
        if not m:
            return 0
    raw = m.group(1).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    mult = 1
    if raw[-1:] in 'KkкК':
        mult, raw = 1_000, raw[:-1]
    elif raw[-1:] in 'MmмМ':
        mult, raw = 1_000_000, raw[:-1]
    try:
        return int(float(raw) * mult)
    except Exception:
        return 0


def _parse_last_post_date(html: str) -> datetime | None:
    # <time datetime="2024-01-15T12:00:00+00:00">
    times = re.findall(r'datetime="([^"]+)"', html)
    parsed = []
    for t in times:
        try:
            dt = datetime.fromisoformat(t)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None) - dt.utcoffset()
            parsed.append(dt)
        except Exception:
            pass
    return max(parsed) if parsed else None


def _has_bot(html: str, bio: str) -> bool:
    # Только bio — в полном HTML 'bot' матчит margin-bottom/roboto (ложные срабатывания)
    return BOT_SIGNALS_RE.search(bio) is not None


def _parse_name(html: str) -> str:
    m = re.search(r'<div class="tgme_page_title"[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'<title>([^<|]+)', html)
    if m:
        return m.group(1).strip()
    return 'Привет'


async def check_channel(username: str) -> dict | None:
    url = f'https://t.me/s/{username}'
    try:
        async with make_session() as s:
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status not in (200, 301, 302):
                    return None
                html = await r.text(errors='replace')
    except Exception as e:
        log.debug(f'check @{username}: {e}')
        return None

    subscribers = _parse_subscribers(html)
    if not (MIN_SUBSCRIBERS <= subscribers <= MAX_SUBSCRIBERS):
        log.info(f'@{username}: {subscribers} подписчиков — пропуск')
        return None

    last_post = _parse_last_post_date(html)
    if last_post:
        age_days = (datetime.now() - last_post).days
        if age_days > MAX_POST_AGE_DAYS:
            log.info(f'@{username}: последний пост {age_days}д назад — пропуск')
            return None
        last_post_str = f'{age_days}д назад' if age_days > 0 else 'сегодня'
    else:
        last_post_str = 'неизвестно'

    # bio
    bio_m = re.search(r'<div class="tgme_page_description"[^>]*>(.*?)</div>', html, re.DOTALL)
    bio = re.sub(r'<[^>]+>', ' ', bio_m.group(1)).strip() if bio_m else ''

    if _has_bot(html, bio):
        log.info(f'@{username}: бот уже есть — пропуск')
        return None

    name = _parse_name(html)
    niche = detect_niche(f'{username} {bio} {html[:2000]}')
    message = build_message(niche, name)

    return {
        'username': username,
        'name': name,
        'niche': niche,
        'subscribers': subscribers,
        'last_post': last_post_str,
        'message': message,
    }


async def checker_loop(notify_queue: asyncio.Queue):
    log.info('checker_loop started')
    while True:
        if notifier._paused:
            await asyncio.sleep(15)
            continue
        row = await database.get_next_from_queue()
        if not row:
            await asyncio.sleep(15)
            continue

        username, query = row
        result = await check_channel(username)
        await database.mark_seen(username)
        await database.mark_checked(username)
        if result:
            await database.save_lead(
                result['username'], result['niche'],
                result['subscribers'], result['last_post'],
                result['message']
            )
            await notify_queue.put(result)
            log.info(f'Лид: @{username} ({result["niche"]}, {result["subscribers"]} подписчиков)')

        sleep = 4 if _is_night() else 2
        await asyncio.sleep(sleep)
