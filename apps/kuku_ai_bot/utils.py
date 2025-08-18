from functools import wraps
from typing import Callable

from asgiref.sync import sync_to_async
from django.utils.timezone import now
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, ContextTypes

from . import translation
from .keyboard import keyboard_checked_subscription_channel, keyboard_check_subscription_channel
from .models import User, SubscribeChannel, Bot


def update_or_create_user(func):
    """
    Decorator that finds or creates a user based on the update
    and passes the user object to the handler.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        if not user_data:
            # Can't proceed without a user, pass to the handler if it can manage.
            return await func(update, context, *args, **kwargs)

        # Get the Django Bot model instance from the context
        bot_instance = context.bot_data.get("bot_instance")
        if not bot_instance:
            # This is a critical error if it happens, should be logged.
            print(f"FATAL: bot_instance not found in context for bot {context.bot.username}")
            return # Stop processing

        # Use Django's async-native ORM method. It's clean and efficient.
        user, created = await User.objects.aupdate_or_create(
            telegram_id=user_data.id,
            bot=bot_instance,
            defaults={
                "first_name": user_data.first_name or "",
                "last_name": user_data.last_name or "",
                "username": user_data.username,
                "stock_language": user_data.language_code,
            }
        )
        # Update last_active on every interaction
        if not created:
            user.last_active = now()
            await user.asave(update_fields=['last_active'])

        user_language = user.selected_language or user.stock_language

        # Pass the user and language to the actual view function
        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper

def channel_subscribe(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        # Foydalanuvchi ma'lumotini olish
        if update.message:
            user_data = update.message.from_user
        elif update.callback_query:
            user_data = update.callback_query.from_user
        else:
            return await func(update, context, *args, **kwargs)

        bot_instance = context.bot_data.get("bot_instance")
        language_code = update.effective_user.language_code if update.effective_user else None

        user, _ = await sync_to_async(User.objects.update_or_create)(
            telegram_id=user_data.id,
            bot=bot_instance,
            defaults={
                "first_name": user_data.first_name or "",
                "last_name": user_data.last_name or "",
                "username": user_data.username or "",
                "last_active": now(),
                "stock_language": language_code,
            },
        )

        user_language = user.selected_language if user.selected_language else user.stock_language

        # Kanal obuna tekshiruvi
        has_active_channels = await SubscribeChannel.objects.filter(active=True).aexists()
        if has_active_channels:
            reply_markup, subscribed_status = await keyboard_checked_subscription_channel(
                user.telegram_id, context.bot.token
            )
            if not subscribed_status:
                if update.message:
                    await update.message.reply_text(
                        translation.subscribe_channel_text[user_language],
                        reply_markup=reply_markup
                    )
                elif update.callback_query:
                    await update.callback_query.answer(
                        translation.subscribe_channel_text[user_language], show_alert=True
                    )
                return  # Obuna bo'lmasa asosiy funksiyani chaqirmaslik

        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        telegram_id = update.effective_user.id
        try:
            user = await sync_to_async(User.objects.get)(
                telegram_id=telegram_id, bot=context.bot_data.get("bot_instance")
            )
        except User.DoesNotExist:
            if update.message:
                await update.message.reply_text("Siz ro'yxatdan o'tmagansiz yoki sizga ruxsat berilmagan.")
            return

        if not user.is_admin:
            if update.message:
                await update.message.reply_text("Ushbu buyruq faqat adminlar uchun!")
            return

        return await func(update, context, *args, user=user, **kwargs)

    return wrapper


def send_typing_action(func: Callable):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.effective_chat:
            await update.effective_chat.send_chat_action(ChatAction.TYPING)
        return await func(update, context, *args, **kwargs)

    return wrapper


def check_subscription_channel_always(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        # Foydalanuvchi va tilni olish
        u, _ = await sync_to_async(User.get_user_and_created)(update, context)
        user_language = u.selected_language or u.stock_language

        # Kanal obuna holatini tekshirish
        reply_markup, subscribed_status = await keyboard_checked_subscription_channel(u.telegram_id)
        if subscribed_status:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text(
                translation.subscribe_channel_text[user_language],
                reply_markup=keyboard_check_subscription_channel()
            )
            return

    return wrapper

