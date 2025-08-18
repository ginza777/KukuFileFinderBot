from django.urls import path
from .webhook import bot_webhook
from .api import TgFileListCreateView, TgFileRetrieveUpdateDestroyView

urlpatterns = [
    path('bot/<str:token>', bot_webhook, name='bot_webhook'),
    path('files/', TgFileListCreateView.as_view(), name='tgfile-list-create'),
    path('files/<int:pk>/', TgFileRetrieveUpdateDestroyView.as_view(), name='tgfile-detail'),
]
