from django.conf import settings
from django.http import HttpResponse


class DevelopmentCorsMiddleware:
    """Permit the Expo web development server to call the mobile API."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        if request.method == 'OPTIONS':
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', set())
        if origin and origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
            response['Vary'] = 'Origin'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        return response
