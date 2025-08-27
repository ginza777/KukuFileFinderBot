# 1. Asosiy image
FROM python:3.12-slim

# Muhit o'zgaruvchilari
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

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
COPY requirements/ ./requirements/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements/production.txt

# 5. Loyiha fayllarini ko‘chirish
COPY . .

# 6. Huquqlari cheklangan foydalanuvchi yaratish
RUN addgroup --system django && adduser --system --ingroup django django

# 7. Media va statik fayllar uchun egalikni berish
# Bu kataloglar docker-compose'da volume sifatida ulanishi mumkin
RUN mkdir -p /app/media /app/static
RUN chown -R django:django /app/media /app/static /app
RUN chmod +x /app/entrypoint.sh

# 8. Yangi foydalanuvchiga o'tish
USER django

# 9. Statik fayllarni to'plash (yangi foydalanuvchi sifatida)
RUN python manage.py collectstatic --no-input

# 10. Port
EXPOSE 8000

# 11. Default buyruq
ENTRYPOINT ["/app/entrypoint.sh"]