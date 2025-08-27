from django.contrib import admin
from django.db import models
from django.db.models import Count

from .forms import SubscribeChannelForm
# --- YANGI MODELLARNI IMPORT QILISH ---
from .models import (Bot, User, Broadcast, BroadcastRecipient,
                     SearchQuery, InvitedUser, Location, SubscribeChannel,
                     TgFile, Category, SubCategory)
# --- ----------------------------- ---
from .tasks import send_message_to_user_task


# --- YANGI ADMIN KLASSLAR ---
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)} # "slug" maydonini avtomatik to'ldirish

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'slug')
    list_filter = ('category',)
    prepopulated_fields = {'slug': ('name',)}
# --- ------------------- ---


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('user', 'latitude', 'longitude', 'created_at')
    search_fields = ('user', 'latitude', 'longitude')
    ordering = ('-id',)


@admin.register(SubscribeChannel)
class SubscribeChannelAdmin(admin.ModelAdmin):
    form = SubscribeChannelForm
    list_display = ("channel_username", "channel_id", "active", "created_at", "updated_at")


class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ('telegram_id', 'first_name', 'last_name', 'username', 'last_active')
    readonly_fields = ('telegram_id', 'first_name', 'last_name', 'username', 'last_active')
    can_delete = False
    show_change_link = True


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ('name', 'token', 'webhook_url')
    search_fields = ('name', 'token')
    inlines = [UserInline]

    def set_webhook_view(self, request, queryset):
        for bot in queryset:
            bot.set_webhook()
        self.message_user(request, "Webhook muvaffaqiyatli o'rnatildi!")

    actions = ['set_webhook_view']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'bot', 'last_active', 'deeplink')
    list_filter = ('bot', 'last_active')
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    readonly_fields = ('bot', 'telegram_id', 'first_name', 'last_name', 'username', 'last_active')


class BroadcastRecipientInline(admin.TabularInline):
    model = BroadcastRecipient
    extra = 0
    fields = ('user', 'status', 'sent_at', 'error_message')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

# --- TgFileAdmin KLASSIGA O'ZGARTIRISH KIRITILDI ---
@admin.register(TgFile)
class TgFileAdmin(admin.ModelAdmin):
    list_display = ('title', 'subcategory', 'file_type', 'uploaded_by', 'uploaded_at', 'size_in_bytes')
    list_filter = ('subcategory', 'file_type', 'require_subscription', 'uploaded_at') # 'subcategory' filtrga qo'shildi
    search_fields = ('title', 'description')
    list_select_related = ('subcategory', 'subcategory__category', 'uploaded_by') # DB so'rovlarini optimallashtirish
# --- -------------------------------------------- ---


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'bot',
        'status',
        'scheduled_time',
        'get_total_recipients',
        'get_sent_count',
        'get_failed_count',
        'get_pending_count',
    )
    list_filter = ('status', 'bot', 'scheduled_time')
    inlines = [BroadcastRecipientInline]
    readonly_fields = (
        'from_chat_id',
        'message_id',
        'created_at',
        'get_total_recipients',
        'get_sent_count',
        'get_failed_count',
        'get_pending_count',
    )
    fields = (
        'bot',
        'status',
        'scheduled_time',
        'from_chat_id',
        'message_id',
        'created_at',
        ('get_total_recipients', 'get_sent_count', 'get_failed_count', 'get_pending_count'),
    )

    actions = ['requeue_failed_recipients']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            total_recipients=Count('recipients'),
            sent_recipients=Count('recipients', filter=models.Q(recipients__status=BroadcastRecipient.Status.SENT)),
            failed_recipients=Count('recipients', filter=models.Q(recipients__status=BroadcastRecipient.Status.FAILED)),
            pending_recipients=Count('recipients',
                                     filter=models.Q(recipients__status=BroadcastRecipient.Status.PENDING)),
        )
        return queryset

    def get_total_recipients(self, obj):
        return obj.total_recipients
    get_total_recipients.short_description = "Jami Qabul Qiluvchilar"

    def get_sent_count(self, obj):
        return obj.sent_recipients
    get_sent_count.short_description = "✅ Yuborilgan"

    def get_failed_count(self, obj):
        return obj.failed_recipients
    get_failed_count.short_description = "❌ Xatolik"

    def get_pending_count(self, obj):
        return obj.pending_recipients
    get_pending_count.short_description = "⏳ Navbatda"

    @admin.action(description="Xatolik bo'lganlarni qayta yuborish")
    def requeue_failed_recipients(self, request, queryset):
        requeued_count = 0
        for broadcast in queryset:
            failed_recipients = broadcast.recipients.filter(status=BroadcastRecipient.Status.FAILED)
            for recipient in failed_recipients:
                send_message_to_user_task.delay(recipient.id)
                requeued_count += 1
            failed_recipients.update(status=BroadcastRecipient.Status.PENDING, error_message=None)
            broadcast.status = Broadcast.Status.PENDING
            broadcast.save()
        self.message_user(request, f"{requeued_count} ta xatolik bo'lgan xabar qayta navbatga qo'yildi.")


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ('query_text', 'user', 'is_deep_search', 'found_results', 'created_at')
    list_filter = ('is_deep_search', 'found_results', 'created_at')
    search_fields = ('query_text', 'user__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(InvitedUser)
class InvitedUserAdmin(admin.ModelAdmin):
    list_display = ( 'first_name', 'channel', 'left', 'invited_at', 'left_at')
    list_filter = ('channel', 'left', 'invited_at')
    readonly_fields = ('invited_at', 'left_at')