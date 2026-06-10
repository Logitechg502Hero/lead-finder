"""Ищет Telegram-каналы малого бизнеса через Telethon SearchRequest."""

import asyncio
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel

import database

load_dotenv()
log = logging.getLogger(__name__)

API_ID         = int(os.environ['TG_API_ID'])
API_HASH       = os.environ['TG_API_HASH']
SESSION_STRING = os.environ['SESSION_STRING']

SEARCH_QUERIES = [
    'барбершоп', 'барбер',
    'фитнес тренер', 'персональный тренер',
    'психолог консультация', 'психотерапевт',
    'коуч', 'наставник',
    'репетитор москва', 'репетитор онлайн',
    'салон красоты', 'парикмахерская',
    'стоматология', 'зубной врач',
    'маникюр педикюр', 'ногтевой сервис',
    'массаж москва', 'массажист',
    'юрист консультация', 'адвокат',
    'бухгалтер услуги', 'налоговый консультант',
    'фотограф москва', 'фотосессия',
    'флорист букеты', 'цветочный магазин',
    'кондитер торты', 'торт на заказ',
    'дизайн интерьера', 'дизайнер интерьера',
    'риэлтор недвижимость', 'агент недвижимости',
    'нутрициолог питание', 'диетолог',
    'логопед занятия', 'детский логопед',
    'визажист макияж', 'свадебный визажист',
    'остеопат', 'мануальный терапевт',
    'натяжные потолки', 'ремонт квартир',
    'юридические услуги', 'правовая помощь',
    'детский центр', 'развивашки',
    'эпиляция воск', 'шугаринг',
    'tattoo тату', 'татуировки',
    'онлайн курс обучение', 'школа онлайн',
]

NIGHT_START = 0
NIGHT_END   = 8


def _is_night() -> bool:
    return NIGHT_START <= datetime.now().hour < NIGHT_END


def _sleep(base: float) -> float:
    return base * 2 if _is_night() else base


async def finder_loop(notify_queue: asyncio.Queue):
    log.info('finder_loop started — Telethon SearchRequest')
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()

    while True:
        for query in SEARCH_QUERIES:
            try:
                result = await client(SearchRequest(q=query, limit=100))
                new_count = 0
                for chat in result.chats:
                    if not isinstance(chat, Channel):
                        continue
                    if not chat.username:
                        continue
                    username = chat.username.lower()
                    if not await database.is_seen(username):
                        await database.queue_for_check(username, query)
                        new_count += 1
                if new_count:
                    log.info(f'[finder] «{query}»: +{new_count} в очередь')
            except Exception as e:
                log.warning(f'[finder] «{query}»: {e}')

            await asyncio.sleep(_sleep(5))

        log.info('[finder] цикл завершён, пауза 30 мин')
        await asyncio.sleep(_sleep(1800))
