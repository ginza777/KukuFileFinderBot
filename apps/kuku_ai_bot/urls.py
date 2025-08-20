from django.urls import path, re_path
from .webhook import bot_webhook
from .api import TgFileListCreateView, TgFileRetrieveUpdateDestroyView

urlpatterns = [
    re_path(r'^bot/(?P<token>.+)/?$', bot_webhook, name='bot_webhook'),
    path('files/', TgFileListCreateView.as_view(), name='tgfile-list-create'),
    path('files/<int:pk>/', TgFileRetrieveUpdateDestroyView.as_view(), name='tgfile-detail'),
]
