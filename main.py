"""
Lead Finder — система поиска лидов в Telegram.
Три параллельных воркера: finder → checker → notifier.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

import database
from finder   import finder_loop
from checker  import checker_loop
from notifier import notifier_loop, bot_polling, bot, MY_CHAT_ID


async def main():
    await database.initialize()
    log.info('БД инициализирована')

    notify_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    await bot.send_message(
        MY_CHAT_ID,
        '🚀 *Lead Finder запущен*\n\n'
        'Ищу Telegram-каналы малого бизнеса без бота.\n\n'
        'Команды:\n'
        '/stats — статистика\n'
        '/queue — очередь на проверку',
        parse_mode='Markdown'
    )

    await asyncio.gather(
        finder_loop(notify_queue),
        checker_loop(notify_queue),
        notifier_loop(notify_queue),
        bot_polling(),
    )


if __name__ == '__main__':
    asyncio.run(main())
