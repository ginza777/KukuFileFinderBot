# 1. Asosiy image
FROM python:3.12-slim

# 2. Ishchi katalog
WORKDIR /app

# 3. Linux paketlarini o‘rnatish
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    netcat-traditional \
    curl \
    file \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 4. requirements.txt o‘rnatish
# Avval toʻliq requirements/ papkasini koʻchiramiz
COPY requirements/ ./requirements/
# Keyin production.txt faylidagi barcha paketlarni oʻrnatamiz
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements/production.txt

# 5. Loyiha fayllarini ko‘chirish
COPY . .

# 6. entrypoint.sh ni executable qilish
RUN chmod +x /app/entrypoint.sh

# 7. Xavfsizlik uchun yangi foydalanuvchi yaratish va ruxsatlarni to'g'rilash
RUN groupadd -r django && useradd -r -g django django
RUN mkdir -p /app/media && chown -R django:django /app/media

# 8. Foydalanuvchini o‘zgartirish
USER django

# 9. Port
EXPOSE 8000

# 10. Default buyruq
ENTRYPOINT ["/app/entrypoint.sh"]