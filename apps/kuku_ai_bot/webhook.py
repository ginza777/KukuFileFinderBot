# webhook.py (Corrected)
import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from telegram import Update

from .handler import get_application
from .models import Bot as BotModel


logger = logging.getLogger(__name__)


@csrf_exempt
async def bot_webhook(request, token):
    """
    Receives webhook requests from Telegram, validates them, and passes
    the update to the application for processing either directly or via Celery.
    """
    bot_instance = await sync_to_async(get_object_or_404)(BotModel, token=token)

    if request.method != "POST":
        return JsonResponse({"status": "invalid request"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.warning("Received invalid JSON in webhook")
        return JsonResponse({"status": "invalid json"}, status=400)

    # Process the update directly in the main thread
    application = get_application(bot_instance.token)

    # Make the bot instance available to handlers/decorators
    application.bot_data["bot_instance"] = bot_instance

    update = Update.de_json(data, application.bot)
    await application.initialize()
    await application.process_update(update)

    return JsonResponse({"status": "ok"})