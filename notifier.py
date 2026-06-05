"""Шлёт лиды в Telegram и принимает нажатия кнопок."""

import asyncio
import logging
import os
from collections import deque
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
)
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

import database
import stats as stats_module

log = logging.getLogger(__name__)

BOT_TOKEN  = os.getenv('BOT_TOKEN')
MY_CHAT_ID = int(os.getenv('MY_CHAT_ID', '0'))

bot = Bot(BOT_TOKEN)
dp  = Dispatcher()

# Ограничение: не более 10 уведомлений в час
_sent_times: deque = deque(maxlen=10)
MAX_PER_HOUR = 10


def _can_send() -> bool:
    now = datetime.now().timestamp()
    while _sent_times and now - _sent_times[0] > 3600:
        _sent_times.popleft()
    return len(_sent_times) < MAX_PER_HOUR


def _lead_kb(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Написал',   callback_data=f'lead_wrote_{username}'),
            InlineKeyboardButton(text='⏭ Пропустить', callback_data=f'lead_skip_{username}'),
        ]
    ])


async def send_lead(lead: dict):
    if not _can_send():
        log.info('Лимит 10/час достигнут — жду...')
        await asyncio.sleep(300)
        return

    username = lead['username']
    text = (
        f'🎯 *Новый лид: @{username}*\n\n'
        f'Ниша: {lead["niche"]}\n'
        f'Подписчики: ~{lead["subscribers"]:,}\n'.replace(',', ' ') +
        f'Последний пост: {lead["last_post"]}\n'
        f'Бот: не найден\n\n'
        f'*📝 Сообщение:*\n'
        f'```\n{lead["message"]}\n```'
    )

    await bot.send_message(
        MY_CHAT_ID, text,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=_lead_kb(username)
    )
    _sent_times.append(datetime.now().timestamp())
    await stats_module.increment_notified()


@dp.callback_query(F.data.startswith('lead_'))
async def handle_lead_action(callback: CallbackQuery):
    parts = callback.data.split('_', 2)
    action, username = parts[1], parts[2]
    outcome = 'wrote' if action == 'wrote' else 'skipped'
    await database.update_lead_outcome(username, outcome)
    if outcome == 'wrote':
        await stats_module.increment_wrote()
        await callback.answer('✅ Записано! Удачи в переговорах 💪', show_alert=True)
    else:
        await callback.answer('⏭ Пропущено', show_alert=False)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@dp.message(F.chat.id == MY_CHAT_ID, F.text == '/stats')
async def cmd_stats(message: Message):
    await message.answer(await stats_module.summary(), parse_mode='Markdown')


@dp.message(F.chat.id == MY_CHAT_ID, F.text == '/queue')
async def cmd_queue(message: Message):
    size = await database.queue_size()
    await message.answer(f'📋 В очереди на проверку: *{size}* каналов', parse_mode='Markdown')


async def notifier_loop(notify_queue: asyncio.Queue):
    log.info('notifier_loop started')
    while True:
        lead = await notify_queue.get()
        try:
            await send_lead(lead)
        except Exception as e:
            log.error(f'send_lead @{lead["username"]}: {e}')
        await asyncio.sleep(5)


async def bot_polling():
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    await dp.start_polling(bot, allowed_updates=['callback_query', 'message'])
