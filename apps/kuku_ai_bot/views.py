# views.py

from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from elasticsearch_dsl.query import QueryString
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import translation
from .documents import TgFileDocument
from .keyboard import (build_search_results_keyboard, default_keyboard,
                     language_list_keyboard, restart_keyboard)
from .models import SearchQuery, TgFile, User
from .utils import (channel_subscribe, get_user,
                    update_or_create_user)

# --- Asosiy Foydalanuvchi Funksiyalari ---

@update_or_create_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    /start buyrug'i uchun. Foydalanuvchini yaratadi yoki oxirgi faolligini yangilaydi.
    """
    if not user.selected_language:
        await ask_language(update, context, user=user, language=language)
    else:
        await update.message.reply_text(
            translation.start_not_created[language].format(user.full_name),
            reply_markup=default_keyboard(language, admin=user.is_admin)
        )

@get_user
async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Tilni tanlash menyusini yuboradi.
    """
    await update.message.reply_text(
        translation.ask_language_text[language],
        reply_markup=language_list_keyboard()
    )

@get_user
async def language_choice_handle(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Callback orqali til tanlovini qayta ishlaydi.
    """
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split("language_setting_")[-1]
    user.selected_language = lang_code
    await user.asave(update_fields=['selected_language'])

    await query.edit_message_text(translation.choice_language[lang_code])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=translation.restart_text[lang_code],
        reply_markup=restart_keyboard(lang=lang_code)
    )

# --- Tugmalar uchun alohida, kichik funksiyalar ---

@update_or_create_user
async def toggle_search_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'Search' va 'Advanced Search' tugmalari bosilganda ishlaydi.
    Talabga ko'ra, bu funksiya foydalanuvchini yangilaydi.
    """
    is_deep = translation.deep_search[language].lower() in update.message.text.lower()
    new_mode = 'deep' if is_deep else 'normal'
    context.user_data['default_search_mode'] = new_mode

    response_text = translation.deep_search_mode_on[language] if new_mode == 'deep' else translation.normal_search_mode_on[language]
    await update.message.reply_text(response_text)

@get_user
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'Help' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.help_message[language])

@get_user
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'About Us' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.about_message[language])

@get_user
async def share_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'Share Bot' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.share_bot_text[language])

# --- Qidiruv va Fayllar Bilan Ishlash ---

@channel_subscribe
@get_user
async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Faqat matnli qidiruv so'rovlari uchun ishlaydi. Obunani tekshiradi.
    """
    text = update.message.text.strip()
    search_mode = context.user_data.get('default_search_mode', 'normal')

    search_fields = ['title^5', 'description^1', 'file_name^4']
    if search_mode == 'deep':
        search_fields.append('content^3')

    s = TgFileDocument.search().query(
        QueryString(query=f"*{text}*", fields=search_fields, default_operator='AND')
    )
    all_files_ids = [int(hit.meta.id) for hit in s.scan()]

    await SearchQuery.objects.acreate(
        user=user, query_text=text, found_results=bool(all_files_ids), is_deep_search=(search_mode == 'deep')
    )

    if not all_files_ids:
        await update.message.reply_text(translation.search_no_results[language].format(query=text))
        return

    context.user_data['last_search_query'] = text
    paginator = Paginator(all_files_ids, 10)
    page_obj = paginator.get_page(1)
    files_on_page = await sync_to_async(list)(TgFile.objects.filter(id__in=page_obj.object_list))

    response_text = translation.search_results_found[language].format(query=text, count=paginator.count)
    reply_markup = build_search_results_keyboard(page_obj, files_on_page, search_mode, language)
    await update.message.reply_text(response_text, reply_markup=reply_markup)

@get_user
async def handle_search_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Qidiruv natijalari sahifalarini o'zgartiradi.
    """
    query = update.callback_query
    await query.answer()

    query_text = context.user_data.get('last_search_query')
    if not query_text:
        await query.edit_message_text(translation.search_no_results[language].format(query=""))
        return

    _, search_mode, page_number_str = query.data.split('_')
    page_number = int(page_number_str)

    search_fields = ['title^5', 'description^1', 'file_name^4']
    if search_mode == 'deep':
        search_fields.append('content^3')

    s = TgFileDocument.search().query(
        QueryString(query=f"*{query_text}*", fields=search_fields, default_operator='AND')
    )
    all_files_ids = [int(hit.meta.id) for hit in s.scan()]

    paginator = Paginator(all_files_ids, 10)
    page_obj = paginator.get_page(page_number)
    files_on_page = await sync_to_async(list)(TgFile.objects.filter(id__in=page_obj.object_list))

    response_text = translation.search_results_found[language].format(query=query_text, count=paginator.count)
    reply_markup = build_search_results_keyboard(page_obj, files_on_page, search_mode, language)
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)


@get_user
async def send_file_by_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Callback orqali faylni yuboradi.
    """
    query = update.callback_query
    file_id = int(query.data.split('_')[1])
    await query.answer()

    try:
        tg_file = await TgFile.objects.aget(id=file_id)
        # Fayl hajmi kattaligi yoki boshqa sabablarga ko'ra yuborishda xatolik bo'lishi mumkin
        await context.bot.send_document(
            chat_id=user.telegram_id,
            document=tg_file.file.path,
            caption=f"<b>{tg_file.title}</b>\n\n{tg_file.description or ''}",
            parse_mode=ParseMode.HTML
        )
    except TgFile.DoesNotExist:
        await context.bot.send_message(chat_id=user.telegram_id, text="Xatolik: Fayl topilmadi.")
    except Exception as e:
        # Faylni yuborishda xatolik bo'lsa, log yozish va foydalanuvchiga xabar berish
        print(f"Fayl yuborishda xatolik: {e}")
        await context.bot.send_message(chat_id=user.telegram_id, text="Faylni yuborishda kutilmagan xatolik yuz berdi.")