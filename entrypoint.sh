#!/bin/sh

# Fayllar saqlanadigan katalog uchun ruxsat berish
chown -R django:django /app/media
chmod -R 755 /app/media

# Wait for the database to be ready
echo "Waiting for postgres..."

# Netcat (nc) yordamida PostgreSQL portini tekshirish
# Bu, bot migratsiyalarni boshlashdan oldin DB ning tayyorligini ta'minlaydi.
while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
  sleep 0.1
done

echo "PostgreSQL started"

# Run database migrations
python manage.py migrate --no-input

# Collect static files
python manage.py collectstatic --no-input

exec "$@"