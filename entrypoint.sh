#!/bin/sh

# Fayllar saqlanadigan katalog uchun ruxsat berish
# Bu endi Dockerfile'da qilinayotgani uchun majburiy emas, lekin qoldirish mumkin.
chown -R django:django /app/media
chmod -R 755 /app/media

# Ma'lumotlar bazasi tayyor bo'lishini kutish
echo "Waiting for postgres..."

# Netcat (nc) yordamida PostgreSQL portini tekshirish
while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
  sleep 0.1
done

echo "PostgreSQL started"

# Ma'lumotlar bazasi migratsiyalarini bajarish
python manage.py migrate --no-input

# Asosiy buyruqni ishga tushirish (masalan, uvicorn)
exec "$@"