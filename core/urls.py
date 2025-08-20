import debug_toolbar
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from . import views
from .swagger.schema import swagger_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path('rosetta/', include('rosetta.urls')),
    path('__debug__/', include(debug_toolbar.urls)),
    # path('', views.index, name="index"),
    path('api/', include('apps.kuku_ai_bot.urls')),
    path('', include('apps.webapp.urls')),
    path('metrics/', include('django_prometheus.urls')),  # YANGI QATOR

]

# swagger
urlpatterns += swagger_urlpatterns

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
