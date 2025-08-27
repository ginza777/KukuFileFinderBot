import logging
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def index(request):
    return JsonResponse({"error": "sup hacker"})

# --- YANGI VIEW ---
def robots_txt(request):
    context = {
        'schema': request.scheme,
        'host': request.get_host(),
    }
    return render(request, 'robots.txt', context, content_type='text/plain')