# services.py

import csv
import io
import logging
import os
import subprocess
from datetime import datetime, timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils.timezone import now

from .models import User

logger = logging.getLogger(__name__)


async def get_user_statistics(bot_username: str) -> dict:
    """
    Foydalanuvchilarning umumiy va oxirgi 24 soatdagi faol soni
    haqida statistika qaytaradi.
    """
    user_count = await User.objects.filter(bot__username=bot_username).acount()
    active_24_count = await User.objects.filter(
        bot__username=bot_username,
        last_active__gte=now() - timedelta(hours=24)
    ).acount()
    return {"total": user_count, "active_24h": active_24_count}


async def perform_database_backup():
    """
    Sozlamalarga qarab ma'lumotlar bazasining zaxira nusxasini yaratadi.
    PostgreSQL va SQLite3'ni qo'llab-quvvatlaydi.

    Returns:
        (fayl_nomi, xatolik_matni) tuple. Muvaffaqiyatli bo'lsa xatolik None bo'ladi.
    """
    db_engine = settings.DATABASES['default']['ENGINE']
    db_config = settings.DATABASES['default']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_file = None
    command = None

    try:
        if 'postgresql' in db_engine:
            dump_file = f"backup_{timestamp}.sql"
            # Xavfsizlik uchun parol subprocess'ga environment orqali uzatiladi
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['PASSWORD']
            command = [
                'pg_dump',
                '-U', db_config['USER'],
                '-h', db_config['HOST'],
                '-p', str(db_config['PORT']),
                db_config['NAME']
            ]
            # `shell=True` ishlatmaslik xavfsizroq
            with open(dump_file, 'w') as f:
                process = await sync_to_async(subprocess.run)(
                    command, check=True, text=True, stdout=f, stderr=subprocess.PIPE, env=env
                )

        elif 'sqlite3' in db_engine:
            dump_file = f"backup_{timestamp}.sqlite3"
            command = f"sqlite3 {db_config['NAME']} .dump > {dump_file}"
            process = await sync_to_async(subprocess.run)(
                command, shell=True, check=True, capture_output=True, text=True
            )
        else:
            return None, "Qo'llab-quvvatlanmaydigan ma'lumotlar bazasi drayveri."

        return dump_file, None

    except subprocess.CalledProcessError as e:
        error_message = f"Zaxira nusxalashda xatolik yuz berdi. Return code: {e.returncode}\nXato: {e.stderr}"
        logger.error(error_message)
        return None, error_message
    except Exception as e:
        error_message = f"Zaxira nusxalashda kutilmagan xatolik: {e}"
        logger.error(error_message)
        return None, error_message


def generate_csv_from_users(users_data) -> io.BytesIO:
    """
    Foydalanuvchilar ma'lumotidan (QuerySet.values()) CSV fayl yaratib,
    uni BytesIO obyekti sifatida qaytaradi.
    """
    if not users_data:
        return io.BytesIO(b"Ma'lumotlar mavjud emas")

    # In-memory matn fayli yaratamiz
    string_io = io.StringIO()
    # Ustun nomlarini birinchi yozuvdan avtomatik olamiz
    writer = csv.DictWriter(string_io, fieldnames=users_data[0].keys())
    writer.writeheader()
    writer.writerows(users_data)

    # Matn faylini boshiga qaytarib, baytlarga o'giramiz
    string_io.seek(0)
    return io.BytesIO(string_io.getvalue().encode('utf-8'))