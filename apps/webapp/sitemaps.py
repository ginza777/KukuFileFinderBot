# apps/webapp/sitemaps.py
from django.contrib.sitemaps import Sitemap
from apps.tg_files.models import TgFile

class TgFileSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return TgFile.objects.all()

    def lastmod(self, obj):
        return obj.uploaded_at