from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
)
from .views import (
    # Asosiy foydalanuvchi funksiyalari
    start,
    ask_language,
    language_choice_handle,

    # Admin funksiyalari
    admin,
    stats,
    backup_db,
    export_users,
    ask_for_location,
    location_handler,
    secret_level,

    # Obuna tekshiruvi
    check_subscription_channel,

    # Reklama yuborish suhbati (o'zgarishsiz qoladi)
    start_broadcast_conversation,
    receive_broadcast_message,
    cancel_broadcast_conversation,
    handle_broadcast_confirmation,
    AWAIT_BROADCAST_MESSAGE,

    # Yangi soddalashtirilgan qidiruv va matn handler'lari
    main_text_handler,
    handle_search_pagination,
    send_file_by_callback,
)

# Bot ilovalari uchun global kesh
telegram_applications = {}


def get_application(token: str) -> Application:
    """
    Berilgan bot tokeni uchun Application obyektini yaratadi yoki keshdan oladi
    va barcha kerakli handler'larni to'g'ri tartibda sozlaydi.
    """
    if token not in telegram_applications:
        application = Application.builder().token(token).build()

        # --- SUHBAT HANDLER'LARI ---
        # Reklama yuborish uchun ConversationHandler (o'zgarishsiz qoladi)
        broadcast_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("broadcast", start_broadcast_conversation)],
            states={
                AWAIT_BROADCAST_MESSAGE: [
                    MessageHandler(~filters.COMMAND, receive_broadcast_message)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_broadcast_conversation)],
        )

        # --- BARCHA HANDLER'LARNING YAGONA RO'YXATI ---
        # Handler'larning tartibi bot mantig'i uchun juda muhim.
        handlers = [
            # 1. SUHBATLAR (buyruqlarni birinchi bo'lib ushlab olishi uchun)
            broadcast_conv_handler,

            # 2. ANIQ BUYRUQLAR (/start, /admin kabi)
            CommandHandler("start", start),
            CommandHandler("admin", admin),
            CommandHandler("stats", stats),
            CommandHandler("backup_db", backup_db),
            CommandHandler("export_users", export_users),
            CommandHandler("ask_location", ask_for_location),

            # 3. CALLBACK SO'ROVLARI (inline tugmalar uchun)
            CallbackQueryHandler(handle_broadcast_confirmation, pattern="^brdcast_"),
            CallbackQueryHandler(handle_search_pagination, pattern="^search_"),
            CallbackQueryHandler(send_file_by_callback, pattern="^getfile_"),
            CallbackQueryHandler(language_choice_handle, pattern="^language_setting_"),
            CallbackQueryHandler(secret_level, pattern="^SCRT_LVL"),
            CallbackQueryHandler(check_subscription_channel, pattern="^check_subscription"),

            # 4. MATNLI XABARLAR UCHUN YAGONA MARKAZIY HANDLER
            # Bu handler barcha tugmalarni va qidiruv so'rovlarini boshqaradi.
            # U ro'yxatning oxirida turishi kerak, chunki u barcha buyruq bo'lmagan matnlarni ushlab oladi.
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_text_handler),

            # 5. BOSHQA TURDAGI XABARLAR (masalan, joylashuv)
            MessageHandler(filters.LOCATION, location_handler),
        ]

        # Barcha handler'larni bitta chaqiruv bilan qo'shamiz
        application.add_handlers(handlers)

        telegram_applications[token] = application

    return telegram_applications[token]