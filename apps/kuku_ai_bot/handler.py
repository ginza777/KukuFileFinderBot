# handler.py

from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ConversationHandler,
)

from .views import (
    start, ask_language, language_choice_handle,
    toggle_search_mode, help_handler, about_handler, share_bot_handler,
    main_text_handler, handle_search_pagination, send_file_by_callback
)
from .admin_views import (
    admin_panel, stats, backup_db, export_users, secret_level,
    ask_location, location_handler  # YANGI FUNKSIYALARNI IMPORT QILAMIZ
)
from .broadcast_views import (
    start_broadcast_conversation, receive_broadcast_message,
    cancel_broadcast_conversation, handle_broadcast_confirmation,
    AWAIT_BROADCAST_MESSAGE
)
from .translation import (
    search, deep_search, help_text, about_us,
    share_bot_button, change_language, admin_button_text, text as restart_text
)

telegram_applications = {}


def get_application(token: str) -> Application:
    if token not in telegram_applications:
        application = Application.builder().token(token).build()

        broadcast_conv = ConversationHandler(
            entry_points=[CommandHandler("broadcast", start_broadcast_conversation)],
            states={AWAIT_BROADCAST_MESSAGE: [MessageHandler(~filters.COMMAND, receive_broadcast_message)]},
            fallbacks=[CommandHandler("cancel", cancel_broadcast_conversation)],
        )

        all_button_texts = [
            *search.values(), *deep_search.values(), *help_text.values(),
            *about_us.values(), *share_bot_button.values(), *change_language.values(),
            admin_button_text, *restart_text.values()
        ]
        button_filter = filters.Text(all_button_texts)

        handlers = [
            broadcast_conv,

            # --- Aniq Buyruqlar ---
            CommandHandler("start", start),
            CommandHandler("help", help_handler),
            CommandHandler("about", about_handler),
            CommandHandler("language", ask_language),

            # --- Admin Buyruqlari ---
            CommandHandler("admin", admin_panel),
            CommandHandler("stats", stats),
            CommandHandler("backup_db", backup_db),
            CommandHandler("export_users", export_users),
            CommandHandler("ask_location", ask_location),  # /ask_location BUYRUG'I QO'SHILDI

            # --- Callback So'rovlari ---
            CallbackQueryHandler(handle_broadcast_confirmation, pattern="^brdcast_"),
            CallbackQueryHandler(handle_search_pagination, pattern="^search_"),
            CallbackQueryHandler(send_file_by_callback, pattern="^getfile_"),
            CallbackQueryHandler(language_choice_handle, pattern="^language_setting_"),
            CallbackQueryHandler(secret_level, pattern="^SCRT_LVL"),

            # --- Tugmalar va Maxsus Xabar Turlari ---
            MessageHandler(filters.Regex(f"^({'|'.join(search.values())}|{'|'.join(deep_search.values())})$"),
                           toggle_search_mode),
            MessageHandler(filters.Regex(f"^({'|'.join(help_text.values())})$"), help_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(about_us.values())})$"), about_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(share_bot_button.values())})$"), share_bot_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(change_language.values())})$"), ask_language),
            MessageHandler(filters.Text(admin_button_text), admin_panel),
            MessageHandler(filters.Regex(f"^({'|'.join(restart_text.values())})$"), start),
            MessageHandler(filters.LOCATION, location_handler),  # YUBORILGAN LOKATSIYANI QABUL QILUVCHI HANDLER

            # --- Qolgan barcha matnli xabarlar (Qidiruv) ---
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~button_filter, main_text_handler),
        ]

        application.add_handlers(handlers)
        telegram_applications[token] = application

    return telegram_applications[token]