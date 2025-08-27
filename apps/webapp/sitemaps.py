# apps/webapp/sitemaps.py
from django.contrib.sitemaps import Sitemap
# XATO IMPORT TUZATILDI:
from apps.kuku_ai_bot.models import TgFile


class TgFileSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9  # Fayl sahifalari muhim bo'lgani uchun priority'ni oshiramiz

    def items(self):
        # Faqat ochiq va obunani talab qilmaydigan fayllarni sitemap'ga qo'shish yaxshiroq
        # Agar barcha fayllar chiqishi kerak bo'lsa, .all() qoldiring
        return TgFile.objects.filter(require_subscription=False).order_by('-uploaded_at')

    def lastmod(self, obj):
        return obj.uploaded_at

    def location(self, obj):
        # Bu yerda har bir fayl uchun to'g'ri URL manzilini hosil qilamiz
        from django.urls import reverse
        return reverse('file-detail', kwargs={'pk': obj.pk})