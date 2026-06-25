from django.conf import settings
from passes.models import Company

class SiteDetectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Clean the host to strip port
        host = request.META.get('HTTP_HOST', '').split(':')[0].lower()
        
        # 2. Check for manual override (header or query param) for testing/local APIs
        vertical_override = request.GET.get('vertical') or request.headers.get('X-Vertical')
        if vertical_override:
            vertical_override = vertical_override.upper()
            if vertical_override in ['TICKETING', 'GYM', 'CAFE', 'GENERIC']:
                request.vertical = vertical_override
                return self.get_response(request)

        # 3. Check hardcoded vertical domains map
        vertical_domains = getattr(settings, 'VERTICAL_DOMAINS', {})
        if host in vertical_domains:
            request.vertical = vertical_domains[host]
            return self.get_response(request)

        # 4. Check custom company domains for future white-label support
        try:
            company = Company.objects.filter(custom_domain=host).first()
            if company:
                request.vertical = company.vertical
            else:
                request.vertical = 'GENERIC'
        except Exception:
            request.vertical = 'GENERIC'

        return self.get_response(request)
