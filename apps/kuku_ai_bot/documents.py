# apps/tg_files/documents.py

from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from tika import parser
from .models import TgFile


@registry.register_document
class TgFileDocument(Document):
    content = fields.TextField(attr='content')

    class Index:
        name = 'tg_files'
        settings = {'number_of_shards': 1, 'number_of_replicas': 0}

    class Django:
        model = TgFile
        fields = [
            'title',
            'description',
            'file_name',
            'file_type',
        ]

    def prepare_content(self, instance):
        """
        Faqat matnli hujjatlar (pdf, doc, other) ichidagi matnni Tika yordamida ajratib oladi.
        Rasm, video, arxiv kabi fayllarni e'tiborsiz qoldiradi.
        """
        # Fayl turini modeldagi tayyor ma'lumotdan olamiz
        file_type = instance.file_type

        # Qaysi turdagi fayllarni o'qish kerakligini belgilaymiz
        text_based_types = ['pdf']  # 'other' ichiga pptx, txt kabi turlar kiradi

        # Agar fayl turi bizga keraklilardan bo'lmasa, bo'sh matn qaytaramiz
        if file_type not in text_based_types:
            return ""

        # Agar fayl mavjud va hajmi 0 dan katta bo'lsa
        if instance.file and instance.file.size > 0:
            try:
                instance.file.open('rb')
                parsed = parser.from_buffer(instance.file.read())
                instance.file.close()

                if parsed and 'content' in parsed and parsed['content']:
                    # Matn ichidagi ortiqcha probel va qatorlarni olib tashlash
                    return ' '.join(str(parsed['content']).split())
            except Exception as e:
                # Agar Tika biror faylni o'qiy olmasa, xatolikni terminalga chiqaradi, lekin dasturni to'xtatmaydi
                print(f"Tika faylni o'qishda xatolik: {instance.file.name}, Xato: {e}")

        return ""