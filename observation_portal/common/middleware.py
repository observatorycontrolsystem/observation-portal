import logging

from django.urls import reverse
from django.shortcuts import redirect

from observation_portal.accounts.models import Profile


class AcceptTermsMiddlware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated and \
                not (request.user.is_staff or request.user.is_superuser or 'api' in request.path):
            try:
                profile = request.user.profile
            except Profile.DoesNotExist:
                profile = Profile.objects.create(user=request.user, institution='', title='')

            if not profile.terms_accepted and request.path != reverse('accept-terms'):
                return redirect(reverse('accept-terms'))

        return response
