# utils.py

from functools import wraps
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

from . import translation
from .keyboard import keyboard_checked_subscription_channel
from .models import User, SubscribeChannel


def update_or_create_user(func: Callable):
    """
    Foydalanuvchini topadi yoki yaratadi. Faqat asosiy kirish nuqtalarida
    (masalan, /start) ishlatilishi kerak.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        bot_instance = context.bot_data.get("bot_instance")
        if not user_data or not bot_instance:
            return

        user, _ = await User.objects.aupdate_or_create(
            telegram_id=user_data.id,
            bot=bot_instance,
            defaults={
                "first_name": user_data.first_name or "",
                "last_name": user_data.last_name or "",
                "username": user_data.username,
                "stock_language": user_data.language_code,
            }
        )
        user_language = user.selected_language or user.stock_language
        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper


def get_user(func: Callable):
    """
    Mavjud foydalanuvchini bazadan oladi. Agar topilmasa, /start ga yo'naltiradi.
    Bu tezkor dekorator bo'lib, bazaga yozish amalini bajarmaydi.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        bot_instance = context.bot_data.get("bot_instance")
        if not user_data or not bot_instance:
            return

        user = await User.objects.filter(telegram_id=user_data.id, bot=bot_instance).afirst()

        if not user:
            # Foydalanuvchi bazada yo'q bo'lsa, uni /start ga yo'naltiramiz.
            lang = user_data.language_code or 'uz'
            if update.message:
                await update.message.reply_text(translation.start_required[lang])
            elif update.callback_query:
                await update.callback_query.answer(translation.start_required[lang], show_alert=True)
            return

        user_language = user.selected_language or user.stock_language
        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper


def channel_subscribe(func: Callable):
    """
    Kanalga obunani tekshiradi. Faqat qidiruv vaqtida ishlatiladi.
    O'zidan oldin @get_user yoki @update_or_create_user ishlatilishiga tayanadi.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = kwargs.get('user')
        user_language = kwargs.get('language')
        if not user or not user_language:
            return await func(update, context, *args, **kwargs)

        has_active_channels = await SubscribeChannel.objects.filter(active=True).aexists()
        if has_active_channels:
            reply_markup, subscribed_status = await keyboard_checked_subscription_channel(user.telegram_id, context.bot)
            if not subscribed_status:
                await update.message.reply_text(
                    translation.subscribe_channel_text.get(user_language),
                    reply_markup=reply_markup
                )
                return
        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_only(func: Callable):
    """Admin huquqini tekshiradi."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = kwargs.get('user')  # @get_user dekoratoridan kelgan user
        if not user or not user.is_admin:
            if update.message:
                await update.message.reply_text("Ushbu buyruq faqat adminlar uchun!")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper
