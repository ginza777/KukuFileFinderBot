from django.utils import timezone

from apps.kuku_ai_bot.models import SubscribeChannel, User, InvitedUser


async def track_group_joins(update, context):
    chat = update.effective_chat
    new_members = update.message.new_chat_members

    # Kanalni yoki guruhni bazadan topish / yaratish
    channel, _ = await SubscribeChannel.objects.aget_or_create(
        channel_id=str(chat.id),
        defaults={
            "channel_username": chat.username,
            "channel_link": f"https://t.me/{chat.username}" if chat.username else None,
            "bot": context.bot_data["bot_instance"],  # Bot model instance
        }
    )

    for member in new_members:
        # Foydalanuvchini bazaga qo'shish
        invited_user, _ = await User.objects.aupdate_or_create(
            telegram_id=member.id,
            bot=context.bot_data["bot_instance"],
            defaults={
                "first_name": member.first_name,
                "last_name": getattr(member, "last_name", ""),
                "username": getattr(member, "username", ""),
            }
        )

        # Kim taklif qilganini aniqlash
        inviter = update.message.from_user
        invited_by, _ = await User.objects.aupdate_or_create(
            telegram_id=inviter.id,
            bot=context.bot_data["bot_instance"],
            defaults={
                "first_name": inviter.first_name,
                "last_name": getattr(inviter, "last_name", ""),
                "username": getattr(inviter, "username", ""),
            }
        )

        # Endi InvitedUser yozuvini yaratish
        await InvitedUser.objects.aupdate_or_create(
            channel=channel,
            invited_by=invited_by,
            invited_user=invited_user,
            defaults={
                "invited_at": timezone.now()
            }
        )
