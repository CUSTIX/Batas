from django.conf import settings


def site(request):
    return {"ai_enabled": bool(settings.GEMINI_API_KEY)}
