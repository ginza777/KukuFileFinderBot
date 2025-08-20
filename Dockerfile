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
COPY requirements/ ./requirements/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements/production.txt

# 5. Loyiha fayllarini ko‘chirish
COPY . .

# 6. entrypoint.sh ni executable qilish
RUN chmod +x /app/entrypoint.sh

# 7. Fayllarga to'liq ruxsat berish
RUN chmod 777 -R /app/

# 8. Statik fayllarni to'plash (root sifatida)
RUN python manage.py collectstatic --no-input

# 9. Port
EXPOSE 8000

# 10. Default buyruq
ENTRYPOINT ["/app/entrypoint.sh"]