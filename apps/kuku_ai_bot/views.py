# views.py (Refactored Version)

import csv
import io
import logging
import os
import subprocess
from datetime import datetime, timedelta

from django.conf import settings
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.timezone import now
from elasticsearch_dsl.query import MultiMatch, QueryString
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes, ConversationHandler

from .documents import TgFileDocument
# Loyihaning lokal modullari
from .keyboard import *
from .models import User, Location, Language, Broadcast, TgFile, SearchQuery  # Language modelini import qilish
from .tasks import start_broadcast_task
from .utils import update_or_create_user, admin_only

logger = logging.getLogger(__name__)

AWAIT_BROADCAST_MESSAGE, AWAIT_SEARCH_QUERY = range(2)


async def get_user_statistics(bot_username: str) -> dict:
    """Foydalanuvchilarning umumiy va faol soni haqida statistika qaytaradi."""
    user_count = await User.objects.filter(bot__username=bot_username).acount()
    active_24_count = await User.objects.filter(
        bot__username=bot_username,
        updated_at__gte=now() - timedelta(hours=24)
    ).acount()
    return {"total": user_count, "active_24h": active_24_count}


async def perform_database_backup():
    """
    Ma'lumotlar bazasining zaxira nusxasini yaratadi.

    WARNING: Tashqi shell komandalarini to'g'ridan-to'g'ri `subprocess` orqali ishga tushirish,
    ayniqsa `shell=True` bilan, xavfsizlik zaifliklariga (masalan, shell injection) olib
    kelishi mumkin. Iloji bo'lsa, Django management commands yoki maxsus kutubxonalardan
    foydalanish tavsiya etiladi.
    """
    db_engine = settings.DATABASES['default']['ENGINE']
    db_config = settings.DATABASES['default']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_file = None
    command = None

    try:
        if 'postgresql' in db_engine:
            dump_file = f"backup_{timestamp}.sql"
            os.environ['PGPASSWORD'] = db_config['PASSWORD']
            command = (
                f"pg_dump -U {db_config['USER']} -h {db_config['HOST']} "
                f"-p {db_config['PORT']} {db_config['NAME']} > {dump_file}"
            )
        elif 'sqlite3' in db_engine:
            dump_file = f"backup_{timestamp}.sqlite3"
            command = f"sqlite3 {db_config['NAME']} .dump > {dump_file}"
        else:
            return None, "Unsupported database engine."

        process = await sync_to_async(subprocess.run)(
            command, shell=True, check=True, capture_output=True, text=True
        )
        return dump_file, None
    except subprocess.CalledProcessError as e:
        logger.error(f"Backup failed. Return code: {e.returncode}\nError: {e.stderr}")
        return None, e.stderr
    except Exception as e:
        logger.error(f"An unexpected error occurred during backup: {e}")
        return None, str(e)


def generate_csv_from_users(users_data) -> io.BytesIO:
    """Foydalanuvchilar ma'lumotidan CSV fayl yaratadi."""
    if not users_data:
        return io.BytesIO(b"No data available")

    string_io = io.StringIO()
    writer = csv.DictWriter(string_io, fieldnames=users_data[0].keys())
    writer.writeheader()
    writer.writerows(users_data)
    string_io.seek(0)
    return io.BytesIO(string_io.getvalue().encode('utf-8'))


# --- User Handlers ---

@update_or_create_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    if user.selected_language is None:
        await ask_language(update, context)
        return

    full_name = user.full_name
    await update.message.reply_text(
        translation.start_not_created[language].format(full_name),
        reply_markup=default_keyboard(language, admin=user.is_admin)
    )


@update_or_create_user
async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    await update.message.reply_text(translation.ask_language_text[language], reply_markup=language_list_keyboard())


@update_or_create_user
async def language_choice_handle(update: Update, context: CallbackContext, user, language):
    query = update.callback_query
    lang_code = query.data.split("language_setting_")[-1]

    # Til nomini hardcode qilish o'rniga, modeldagi `choices`dan olish mumkin
    # Masalan: lang_name = Language(lang_code).label
    lang_name = dict(Language.choices).get(lang_code, lang_code.capitalize())

    user.selected_language = lang_code
    await sync_to_async(user.save)()

    await query.answer(f"{translation.choice_language[lang_code]} {lang_name}")
    await query.edit_message_text(f"{translation.choice_language[lang_code]} {lang_name}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=translation.restart_text[lang_code],
        reply_markup=restart_keyboard(lang=lang_code)
    )


@update_or_create_user
async def about(update: Update, context: CallbackContext, user, language) -> None:
    reply_markup = make_keyboard_for_about_command(language, admin=user.is_admin)
    await update.message.reply_text(
        translation.about_message[language],
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )


@update_or_create_user
async def help(update: Update, context: CallbackContext, user, language) -> None:
    text = translation.start_not_created[language].format(user.full_name)
    await update.message.reply_text(
        text + translation.help_message[language],
        parse_mode=ParseMode.HTML,
        reply_markup=make_keyboard_for_help_command()
    )


@update_or_create_user
async def share_bot(update: Update, context: CallbackContext, user, language) -> None:
    await update.message.reply_text(
        translation.share_bot_text[language],
        reply_markup=share_bot_keyboard(lang=language)
    )


@update_or_create_user
async def ask_for_location(update: Update, context: CallbackContext, user, language) -> None:
    await context.bot.send_message(
        chat_id=user.telegram_id,
        text=translation.share_location,
        reply_markup=send_location_keyboard()
    )


@update_or_create_user
async def location_handler(update: Update, context: CallbackContext, user, language) -> None:
    location = update.message.location
    await Location.objects.acreate(user=user, latitude=location.latitude, longitude=location.longitude)
    await update.message.reply_text(
        translation.thanks_for_location,
        reply_markup=default_keyboard(language, admin=user.is_admin)
    )


@update_or_create_user
async def check_subscription_channel(update: Update, context: CallbackContext, user, language) -> None:
    query = update.callback_query
    reply_markup, subscribed_status = await keyboard_checked_subscription_channel(user.telegram_id, context.bot)

    if query.message.reply_markup == reply_markup:
        await query.answer()  # Foydalanuvchiga hech narsa o'zgarmaganini bildirish
        return

    if subscribed_status:
        await query.edit_message_text(translation.full_permission[language])
    else:
        await query.edit_message_reply_markup(reply_markup)
        await query.answer(translation.not_subscribed[language], show_alert=True)


# --- Admin Handlers ---

@admin_only
async def admin(update: Update, context: CallbackContext, user) -> None:
    await update.message.reply_text(translation.secret_admin_commands)


@admin_only
async def stats(update: Update, context: CallbackContext, user) -> None:
    stats_data = await get_user_statistics(context.bot.username)
    text = translation.users_amount_stat.format(
        user_count=stats_data["total"],
        active_24=stats_data["active_24h"]
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def backup_db(update: Update, context: CallbackContext, user) -> None:
    await update.message.reply_text("⏳ Starting database backup...")
    dump_file, error = await perform_database_backup()

    if dump_file and not error:
        try:
            with open(dump_file, 'rb') as f:
                await update.message.reply_document(document=f, filename=dump_file,
                                                    caption="Database backup successful.")
        finally:
            os.remove(dump_file)  # Faylni yuborilgandan keyin o'chirish
    else:
        await update.message.reply_text(f"🔴 Failed to perform database backup. Error:\n{error}")


@admin_only
async def export_users(update: Update, context: CallbackContext, user) -> None:
    users_data = await sync_to_async(list)(User.objects.values())
    csv_file = await sync_to_async(generate_csv_from_users)(users_data)

    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=csv_file,
        filename="users_export.csv",
        caption="Exported user data."
    )


@admin_only
async def secret_level(update: Update, context: CallbackContext, user) -> None:
    query = update.callback_query
    stats_data = await get_user_statistics(context.bot.username)
    lang = user.selected_language or user.stock_language
    text = translation.unlock_secret_room[lang].format(
        user_count=stats_data["total"],
        active_24=stats_data["active_24h"]
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def start_broadcast_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> int:
    """Admindan reklama xabarini forward qilishni so'raydi."""
    await update.message.reply_text(
        "Reklama uchun tayyor xabarni forward qiling.\n"
        "Suhbatni bekor qilish uchun /cancel buyrug'ini bering."
    )
    return AWAIT_BROADCAST_MESSAGE


@admin_only
async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> int:
    """Admin tomonidan yuborilgan xabarni inline tugmalar bilan tasdiqlashga chiqaradi."""
    message = update.message
    callback_prefix = f"brdcast_{message.chat_id}_{message.message_id}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Hozir yuborish", callback_data=f"{callback_prefix}_send_now")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"{callback_prefix}_cancel")]
    ])

    await update.message.reply_text(
        "Ushbu xabar barcha foydalanuvchilarga yuborilsinmi?", reply_markup=keyboard
    )
    return ConversationHandler.END


@admin_only
async def cancel_broadcast_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> int:
    """Suhbatni bekor qiladi."""
    await update.message.reply_text("Reklama yaratish bekor qilindi.")
    return ConversationHandler.END


@admin_only
async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Tasdiqlash tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()

    data = query.data.split('_')
    action = data[-1]
    from_chat_id = int(data[1])
    message_id = int(data[2])

    bot_instance = context.bot_data.get("bot_instance")
    print("Action:", action)

    if action == "cancel":
        await query.edit_message_text("❌ Reklama bekor qilindi.")
        return

    if action == "now":
        await query.edit_message_text("⏳ Yuborilmoqda...")
        broadcast = await Broadcast.objects.acreate(
            bot=bot_instance,
            from_chat_id=from_chat_id,
            message_id=message_id,
            scheduled_time=timezone.now(),
            status=Broadcast.Status.PENDING
        )

        # Bazaga yozilishi tugashini kutib bo'lgach, Celery task chaqirish
        start_broadcast_task.delay(broadcast.id)
        await query.edit_message_text(f"✅ Reklama (ID: {broadcast.id}) navbatga qo'yildi!")


# search
@update_or_create_user
async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Botga kelgan barcha matnli xabarlarni boshqaradigan markaziy funksiya.
    """
    text = update.message.text.lower()

    # 1-PRIORITET: Tugma matnlarini tekshirish (o'zgarishsiz)
    if text in [translation.search[language].lower(), translation.deep_search[language].lower()]:
        return await toggle_search_mode(update, context)
    elif text == translation.change_language[language].lower():
        return await ask_language(update, context)
    elif text == translation.help_text[language].lower():
        return await help(update, context)
    elif text == translation.about_us[language].lower():
        return await about(update, context)
    elif text == translation.share_bot_button[language].lower():
        return await share_bot(update, context)

    search_mode = context.user_data.get('default_search_mode', 'normal')

    search_fields = []
    if search_mode == 'deep':
        # Fayl ichi va boshqa maydonlar uchun ustunlik
        search_fields = ['title^2', 'description^1', 'file_name^1', 'content^3']
    else:  # normal
        # Sarlavha va fayl nomiga yuqori ustunlik
        search_fields = ['title^5', 'description^1', 'file_name^4']

    # --- O'ZGARTIRILGAN QISM ---
    # MultiMatch o'rniga QueryString dan foydalanamiz
    # Bu foydalanuvchi kiritgan so'zning oldidan va orqasidan * belgisini qo'yadi.
    # Masalan, "res" so'rovi "*res*" ga aylanadi va "resume" so'zining ichidan topiladi.
    s = TgFileDocument.search().query(
        QueryString(
            query=f"*{text}*",  # So'rovni wildcard bilan o'raymiz
            fields=search_fields,
            default_operator='AND'  # Agar bir nechta so'z kiritilsa, hammasi qatnashishi shart
        )
    )
    # --- O'ZGARTIRISH TUGADI ---

    all_files_ids = [int(hit.meta.id) for hit in s.scan()]

    await SearchQuery.objects.acreate(
        user=user, query_text=text, found_results=bool(all_files_ids), is_deep_search=(search_mode == 'deep')
    )

    if not all_files_ids:
        await update.message.reply_text(translation.search_no_results[language].format(query=text))
        return

    # Natijalarni saralash (bu qism kerak bo'lmasligi mumkin, chunki QueryString o'zi saralaydi)
    s = s.sort({"_score": {"order": "desc"}})

    paginator = Paginator(all_files_ids, 10)
    page_obj = paginator.get_page(1)

    # Muhim: Paginator bilan to'g'ri ishlash uchun so'rovni saqlab qo'yish kerak
    context.user_data['last_search_query'] = text

    files_on_page = await sync_to_async(list)(TgFile.objects.filter(id__in=page_obj.object_list))

    response_text = translation.search_results_found[language].format(query=text, count=paginator.count)

    # build_search_results_keyboard funksiyasiga 'text' argumentini olib tashlaymiz
    reply_markup = build_search_results_keyboard(page_obj, files_on_page, search_mode, language)

    await update.message.reply_text(response_text, reply_markup=reply_markup)

@update_or_create_user
async def handle_search_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User,
                                   language: str) -> None:
    query = update.callback_query
    await query.answer()

    # Retrieve the search query from user_data
    query_text = context.user_data.get('last_search_query')
    if not query_text:
        await query.edit_message_text("Xatolik: So'rov topilmadi. Iltimos, qayta qidiring.")
        return

    parts = query.data.split('_')
    search_type, page_number = parts[1], int(parts[2])

    if search_type == 'deep':
        search_fields = ['title^2', 'description', 'file_name', 'content^3']
    else:
        search_fields = ['title^4', 'description^2', 'file_name']

    s = TgFileDocument.search().query(
        MultiMatch(query=query_text, fields=search_fields, fuzziness='AUTO')
    ).sort({"_score": {"order": "desc"}})

    all_files_ids = [int(hit.meta.id) for hit in s.scan()]

    if not all_files_ids:
        await query.edit_message_text("Natijalar topilmadi.")
        return

    paginator = Paginator(all_files_ids, 10)
    page_obj = paginator.get_page(page_number)
    files_on_page = await sync_to_async(list)(TgFile.objects.filter(id__in=page_obj.object_list))

    response_text = translation.search_results_found[language].format(query=query_text, count=paginator.count)
    # Pass the query text for display, not for the callback data
    reply_markup = build_search_results_keyboard(page_obj, files_on_page, search_type, language)

    await query.edit_message_text(text=response_text, reply_markup=reply_markup)


@update_or_create_user
async def toggle_search_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    "Search" va "Advanced Search" tugmalari bosilganda standart qidiruv rejimini o'zgartiradi.
    """
    message_text = update.message.text

    is_deep = 'Kengaytirilgan' in message_text or 'Расширенный' in message_text or 'Advanced' in message_text or 'Gelişmiş' in message_text
    new_mode = 'deep' if is_deep else 'normal'

    context.user_data['default_search_mode'] = new_mode

    if new_mode == 'deep':
        response_text = translation.deep_search_mode_on[language]
    else:
        response_text = translation.normal_search_mode_on[language]

    await update.message.reply_text(response_text)


@update_or_create_user
async def handle_search_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User,
                                   language: str) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_', 3)
    search_type, page_number, query_text = parts[1], int(parts[2]), parts[3]

    # Qidiruvni qaytadan bajarish - bu eng barqaror usul
    if search_type == 'deep':
        search_fields = ['title^2', 'description', 'file_name', 'content^3']
    else:
        search_fields = ['title^4', 'description^2', 'file_name']

    s = TgFileDocument.search().query(
        MultiMatch(query=query_text, fields=search_fields, fuzziness='AUTO')
    )
    all_files_ids = [int(hit.meta.id) for hit in s.scan()]

    if not all_files_ids:
        await query.edit_message_text("Natijalar topilmadi.")
        return

    paginator = Paginator(all_files_ids, 10)
    page_obj = paginator.get_page(page_number)
    files_on_page = await sync_to_async(list)(TgFile.objects.filter(id__in=page_obj.object_list))

    response_text = translation.search_results_found[language].format(query=query_text, count=paginator.count)
    reply_markup = build_search_results_keyboard(page_obj, files_on_page, search_type, query_text, language)

    await query.edit_message_text(text=response_text, reply_markup=reply_markup)


@update_or_create_user
async def send_file_by_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """ Inline tugma orqali faylni yuboradi. """
    query = update.callback_query
    await query.answer()

    file_id = int(query.data.split('_')[1])

    try:
        file_to_send = await TgFile.objects.aget(id=file_id)
        # Faylni yuborish mantiqi (eski kodingizdan olingan va asinxronga moslangan)
        # Bu qism uchun `send_file_to_user` funksiyasini asinxron qilib qayta yozish kerak
        # yoki shu yerda logikani takrorlash kerak.
        await context.bot.send_document(
            chat_id=user.telegram_id,
            document=file_to_send.file,
            filename=file_to_send.file_name,
            caption=file_to_send.title
        )
    except TgFile.DoesNotExist:
        await context.bot.send_message(chat_id=user.telegram_id, text="Xatolik: Fayl topilmadi.")
    except Exception as e:
        await context.bot.send_message(chat_id=user.telegram_id, text=f"Faylni yuborishda xatolik: {e}")
