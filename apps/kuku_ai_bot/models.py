# models.py (Refactored and Optimized Version)
import asyncio
import logging
import os  # fayl kengaytmasini olish uchunk
import asyncio
from telegram.error import TelegramError

import magic  # "python-magic" kutubxonasini import qilamiz
import requests
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from telegram import Bot as TelegramBot
from telegram.error import TelegramError

# Katta loyihalarda print o'rniga logging dan foydalanish tavsiya etiladi
logger = logging.getLogger(__name__)

# --- Constants ---
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


# --- Telegram API Utility Functions ---
# Izoh: Katta loyihalarda bu funksiyalarni alohida services.py fayliga ko'chirish maqsadga muvofiq.

def get_bot_details_from_telegram(token: str) -> tuple[str, str]:
    """
    Fetches bot's first_name and username from the Telegram API using its token.

    Args:
        token: The Telegram bot token.

    Returns:
        A tuple containing the bot's first_name and username.

    Raises:
        ValidationError: If the API request fails or the token is invalid.
    """
    url = TELEGRAM_API_URL.format(token=token, method="getMe")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # HTTP xatolar uchun xatolikni ko'taradi (4xx, 5xx)
        data = response.json()
        if data.get("ok"):
            result = data["result"]
            return result["first_name"], result["username"]
        else:
            raise ValidationError(_("Failed to get bot information. API response not OK."))
    except requests.RequestException as e:
        logger.error(f"Telegram API request failed: {e}")
        raise ValidationError(_("Could not connect to Telegram API."))
    except (KeyError, TypeError) as e:
        logger.error(f"Unexpected API response structure: {e}")
        raise ValidationError(_("Invalid response received from Telegram API."))


def register_bot_webhook(bot_token: str, webhook_base_url: str) -> str:
    """
    Sets the bot's webhook on Telegram.

    Args:
        bot_token: The Telegram bot token.
        webhook_base_url: The base URL for the webhook (e.g., from settings).

    Returns:
        The full webhook URL that was set.

    Raises:
        ValidationError: If the webhook registration fails.
    """
    full_webhook_url = f"{webhook_base_url}/api/bot/{bot_token}"
    url = TELEGRAM_API_URL.format(token=bot_token, method=f"setWebhook?url={full_webhook_url}")
    try:
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        if not response.json().get("ok"):
            raise ValidationError(
                _("Telegram API rejected the webhook setup: {description}").format(
                    description=response.json().get("description", "Unknown error")
                )
            )
        return full_webhook_url
    except requests.RequestException as e:
        logger.error(f"Failed to set webhook for bot {bot_token[:10]}...: {e}")
        raise ValidationError(_("Failed to register webhook with Telegram API."))


async def check_bot_is_admin_in_channel(channel_id: str, telegram_token: str) -> bool:
    """
    Asynchronously checks if the bot is an administrator in a given channel.

    Args:
        channel_id: The ID of the Telegram channel.
        telegram_token: The bot's token.

    Returns:
        True if the bot is an admin, False otherwise.
    """
    logger.info(f"Checking admin status for bot in channel {channel_id}")
    try:
        bot = TelegramBot(token=telegram_token)
        bot_info = await bot.get_me()
        print(bot_info)
        admins = await bot.get_chat_administrators(chat_id=channel_id)
        print("Admins in channel:", admins)
        return any(admin.user.id == bot_info.id for admin in admins)
    except TelegramError as e:
        logger.error(f"Telegram error while checking admin status in {channel_id}: {e}")
        return False


# --- Custom Managers ---

class GetOrNoneManager(models.Manager):
    """
    Custom manager with a `get_or_none` method that returns None
    if the object does not exist, instead of raising an exception.
    """

    async def get_or_none(self, **kwargs):
        """Asynchronously fetches an object or returns None if it doesn't exist."""
        try:
            return await sync_to_async(self.get)(**kwargs)
        except ObjectDoesNotExist:
            return None


# --- Models ---


class Bot(models.Model):
    """
    Represents a Telegram bot registered in the system.
    """
    name = models.CharField(max_length=100, blank=True, help_text=_("Auto-filled from Telegram API on save"))
    username = models.CharField(max_length=100, blank=True, help_text=_("Auto-filled from Telegram API on save"))
    token = models.CharField(max_length=255, unique=True, help_text=_("The unique token provided by @BotFather"))
    webhook_url = models.URLField(max_length=255, blank=True, help_text=_("Auto-filled on save"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Bot")
        verbose_name_plural = _("Bots")

    def __str__(self):
        return self.name or self.username or _("Unnamed Bot")

    def _fetch_and_set_bot_info(self):
        """Helper method to get bot info from Telegram and set it on the model instance."""
        self.name, self.username = get_bot_details_from_telegram(self.token)

    def _register_webhook(self):
        """Helper method to register the webhook URL with Telegram."""
        # Muhim: settings.WEBHOOK_URL sozlamalarda mavjud bo'lishi kerak.
        if not hasattr(settings, 'WEBHOOK_URL'):
            raise ValidationError(_("WEBHOOK_URL is not configured in Django settings."))
        self.webhook_url = register_bot_webhook(self.token, settings.WEBHOOK_URL)

    def save(self, *args, **kwargs):
        """
        Overrides the default save method to fetch bot details and set the webhook.

        WARNING: Performing external API calls within a model's `save` method is
        generally discouraged as it can slow down database transactions and
        make the save operation fail due to network issues. A better approach
        for production systems is to use a background task (e.g., Celery)
        or a custom admin command/action to provision a new bot.
        """
        is_new = self._state.adding
        if is_new:  # Faqat yangi bot yaratilayotganda ishga tushadi
            try:
                self._fetch_and_set_bot_info()
                self._register_webhook()
            except ValidationError as e:
                # Xatolikni to'g'ridan-to'g'ri yuqoriga uzatish,
                # bu admin panelida xabarni ko'rsatadi.
                raise e
        super().save(*args, **kwargs)


class SubscribeChannel(models.Model):
    """
    Represents a Telegram channel that users must subscribe to.
    """
    channel_username = models.CharField(max_length=100, unique=True, null=True, blank=True)
    channel_link = models.URLField(max_length=255, blank=True, null=True)
    channel_id = models.CharField(max_length=100, unique=True)
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="subscription_channels",
                            help_text=_("The bot that manages this channel."))
    active = models.BooleanField(default=True)
    private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Subscription Channel")
        verbose_name_plural = _("Subscription Channels")
        ordering = ["-created_at"]

    def __str__(self):
        return self.channel_username or self.channel_id

    def clean(self):
        """
        Custom validation for the model.
        """
        if self.private and not self.channel_link:
            raise ValidationError(_("A private channel must have an invitation link."))
        if not self.private and not self.channel_username:
            raise ValidationError(_("A public channel must have a username."))

        # --- O'ZGARTIRILGAN QISM ---
        if self.bot and self.bot.token and self.channel_id:
            try:
                # Sinxron `clean` metodi ichidan asinxron funksiyani
                # `asyncio.run()` yordamida ishga tushiramiz.
                is_admin = asyncio.run(
                    check_bot_is_admin_in_channel(self.channel_id, self.bot.token)
                )
                print(f"Admin status for {self.channel_id}: {is_admin}")

                # Mantiq to'g'irlandi: Agar bot admin bo'lmasa, xatolik berish kerak.
                if not is_admin:
                    raise ValidationError(
                        _("The bot is not an administrator in the specified channel. Please add the bot as an admin and try again.")
                    )
            except TelegramError as e:
                # Telegram API'dan keladigan maxsus xatoliklarni ushlab olamiz
                raise ValidationError(f"Telegram API error: {e.message}")
            except Exception as e:
                # Boshqa kutilmagan xatoliklar uchun
                raise ValidationError(f"Failed to verify bot admin status: {e}")

    def save(self, *args, **kwargs):
        """
        Strips prefixes from the username before saving.
        """
        if self.channel_username:
            self.channel_username = self.channel_username.removeprefix("https://t.me/").removeprefix("@")
        super().save(*args, **kwargs)

    @property
    def get_channel_link(self) -> str | None:
        """Returns the full, clickable link for a public channel."""
        if self.private:
            return self.channel_link
        return f"https://t.me/{self.channel_username}"


class Language(models.TextChoices):
    UZ = 'uz', _('Uzbek')
    RU = 'ru', _('Russian')
    EN = 'en', _('English')
    TR = 'tr', _('Turkish')


class User(models.Model):
    """
    Represents a Telegram user interacting with one of the bots.
    """
    telegram_id = models.BigIntegerField()
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="users")
    is_admin = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stock_language = models.CharField(max_length=10, choices=Language.choices, default=Language.UZ)
    selected_language = models.CharField(max_length=10, choices=Language.choices, null=True, blank=True)
    deeplink = models.TextField(blank=True, null=True)
    left = models.BooleanField(default=False)

    class Meta:
        unique_together = ('telegram_id', 'bot')
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return f"{self.full_name} ({self.telegram_id}) - Bot: {self.bot.name}"

    @property
    def full_name(self) -> str:
        """Returns the user's full name."""
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class Location(models.Model):
    """
    Stores location data sent by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="locations")
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GetOrNoneManager()

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Location for {self.user} at {self.created_at.strftime('(%H:%M, %d %B %Y)')}"


class Broadcast(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')

    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, related_name="broadcasts")
    from_chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    def __str__(self):
        return f"Forward {self.message_id} from {self.from_chat_id}"


class BroadcastRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SENT = 'sent', _('Sent')
        FAILED = 'failed', _('Failed')

    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name="broadcast_messages")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('broadcast', 'user')


class SearchQuery(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_queries')
    query_text = models.CharField(max_length=500)
    found_results = models.BooleanField(default=False)
    is_deep_search = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.query_text}' by {self.user}"


def upload_to(instance, filename):
    return f'files/{timezone.now().year}/{timezone.now().month}/{filename}'


class TgFile(models.Model):
    FILE_TYPE_CHOICES = (
        ('pdf', 'PDF'),
        ('doc', 'DOC/DOCX'),
        ('zip', 'ZIP/Archive'),
        ('media', 'Media'),  # Rasm, video, audio uchun umumiy
        ('other', 'Other'),
    )

    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to=upload_to)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='other')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    size_in_bytes = models.BigIntegerField(default=0)
    require_subscription = models.BooleanField(default=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['file_type']),
        ]

    def save(self, *args, **kwargs):
        # Fayl hajmini avtomatik hisoblash (bu qism avval ham bor edi)
        if self.file and not self.size_in_bytes:
            self.size_in_bytes = self.file.size

        # --- FAYL TURINI AVTOMATIK ANIQLASH QISMI ---
        # Agar fayl yangi yuklangan bo'lsa
        if self.file and not self._state.adding is False:
            # Faylning boshlang'ich 2KB ma'lumotini o'qib, turini (MIME type) aniqlaymiz
            # Bu fayl nomidan ko'ra ancha ishonchli usul
            self.file.seek(0)  # Fayl o'qishni boshidan boshlash
            mime_type = magic.from_buffer(self.file.read(2048), mime=True)
            self.file.seek(0)  # Fayl o'qishni yana boshiga qaytaramiz, Django saqlashi uchun

            # Aniqlangan MIME type'ga qarab o'zimizning kategoriyani tanlaymiz
            if 'pdf' in mime_type:
                self.file_type = 'pdf'
            elif 'zip' in mime_type or 'rar' in mime_type or '7z' in mime_type:
                self.file_type = 'zip'
            elif 'word' in mime_type or 'document' in mime_type:
                self.file_type = 'doc'
            elif 'image' in mime_type or 'video' in mime_type or 'audio' in mime_type:
                self.file_type = 'media'
            else:
                self.file_type = 'other'

        # Fayl nomini "title" ga avtomatik qo'yish (agar bo'sh bo'lsa)
        if not self.title and self.file:
            # Fayl nomidan kengaytmasini olib tashlaymiz
            self.title = os.path.splitext(os.path.basename(self.file.name))[0]
        if self.file:
            self.file_name = os.path.basename(self.file.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# models.py

class InvitedUser(models.Model):
    """
    Tracks which user invited another user to a specific subscription channel.
    """
    channel = models.ForeignKey(
        SubscribeChannel,
        on_delete=models.CASCADE,
        related_name='invited_members',
        verbose_name=_("Channel")
    )
    invited_by = models.ForeignKey(
        User,  # bu bot foydalanuvchisi (kim taklif qildi)
        on_delete=models.CASCADE,
        related_name='invited_users',
        verbose_name=_("Invited By")
    )
    telegram_id = models.BigIntegerField()
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    invited_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Invited At"))
    left = models.BooleanField(default=False, verbose_name=_("Left the Channel"))
    left_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Left At"))

    class Meta:
        verbose_name = _("Invited User")
        verbose_name_plural = _("Invited Users")
        # Bir foydalanuvchi bir kanalga faqat bir marta taklif qilinishi mumkin
        unique_together = ('channel', 'telegram_id')
        ordering = ['-invited_at']

    def __str__(self):
        status = "left" if self.left else "active"
        return f"{self.first_name or ''} {self.last_name or ''} (@{self.username}) [{status}]"
