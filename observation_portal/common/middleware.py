import logging

from observation_portal.accounts.models import Profile
from django.conf import settings
from django.http import HttpResponseBadRequest
from rest_framework.authentication import TokenAuthentication
from rest_framework.request import Request

class RequestLogMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('portal_request')

    def __call__(self, request):
        response = self.get_response(request)

        try:
            username = request.user.username
            simple_interface = request.user.profile.simple_interface
        except (AttributeError, Profile.DoesNotExist):
            simple_interface = False
            username = 'anonymous'

        forwarded_ip = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_ip:
            ip_address = forwarded_ip.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        tags = {
            'ip_address': ip_address,
            'uri': request.path,
            'status': response.status_code,
            'method': request.method,
            'user': username,
            'simple_interface': simple_interface,
        }

        if response.status_code >= 400:
            level = logging.WARN
        else:
            level = logging.INFO

        self.logger.log(level, 'PortalRequestLog', extra={'tags': tags})

        return response


class LimitAnonymousAccessMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If this is an unauthenticated GET request, check the offset and limit and block if theyre too large
        if request.method == 'GET' and not request.user.is_authenticated:
            offset = request.GET.get('offset')
            if offset and offset.isdigit() and int(offset) > settings.MAX_UNAUTHENTICATED_OFFSET:
                return HttpResponseBadRequest("Large offset not allowed for anonymous users.")

            limit = request.GET.get('limit')
            if limit and limit.isdigit() and int(limit) > settings.MAX_UNAUTHENTICATED_LIMIT:
                return HttpResponseBadRequest("Large limit not allowed for anonymous users.")

        return self.get_response(request)


class DRFTokenAuthMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is a Token Auth request based on the Auth header having `Token` in it.
        if request.method == 'GET' and request.headers.get('Authorization', '').startswith('Token'):
            drf_request = Request(request)
            try:
                user_auth = TokenAuthentication().authenticate(drf_request)
                # Set the request.user field if we successfully authenticate with TokenAuthentication
                if user_auth:
                    request.user = user_auth[0]
            except Exception:
                pass
        return self.get_response(request)
