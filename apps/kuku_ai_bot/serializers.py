from rest_framework import serializers
from .models import TgFile

class TgFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TgFile
        fields = '__all__'
        read_only_fields = ('uploaded_at', 'uploaded_by', 'size_in_bytes')