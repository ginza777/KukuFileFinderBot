# apps/webapp/urls.py

from django.urls import path
from .views import FileListView,FileDetailView

urlpatterns = [
    path('', FileListView.as_view(), name='file-list'),
    path('file/<int:pk>/', FileDetailView.as_view(), name='file-detail'),
]