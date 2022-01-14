from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.utils.functional import cached_property
import uuid
import logging
from datetime import timedelta
from django.contrib.auth.models import User
from oauth2_provider.models import AccessToken, Application
from rest_framework.authtoken.models import Token

from observation_portal.proposals.models import Proposal

logger = logging.getLogger()


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    institution = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    education_user = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=False)
    notifications_on_authored_only = models.BooleanField(default=False)
    simple_interface = models.BooleanField(default=False)
    view_authored_requests_only = models.BooleanField(default=False)
    staff_view = models.BooleanField(default=False)
    terms_accepted = models.DateTimeField(blank=True, null=True)

    def time_used_in_proposal(self, proposal):
        if not proposal.current_semester:
            return 0
        requestgroups = self.user.requestgroup_set.filter(
            proposal=proposal, created__gte=proposal.current_semester.start, state__in=['PENDING', 'COMPLETED']
        ).prefetch_related('requests')
        return sum(
            request.duration for request_group in requestgroups for request in request_group.requests.filter(
                state__in=['PENDING', 'COMPLETED']
            )
        )

    @property
    def archive_bearer_token(self):
        # During testing, you will probably have to copy access tokens from prod for this to work
        try:
            app = Application.objects.get(name='Archive')
        except Application.DoesNotExist:
            logger.error('Archive application not found. Oauth applications need to be populated.')
            return ''
        access_token = AccessToken.objects.filter(user=self.user, application=app, expires__gt=timezone.now()).last()
        if not access_token:
            access_token = AccessToken(
                user=self.user,
                application=app,
                token=uuid.uuid4().hex,
                expires=timezone.now() + timedelta(days=30)
            )
            access_token.save()
        return access_token.token

    @cached_property
    def current_proposals(self):
        return Proposal.current_proposals().filter(active=True, membership__user=self.user).distinct()

    @property
    def api_token(self):
        return Token.objects.get_or_create(user=self.user)[0]

    @property
    def api_quota(self):
        '''Get's the amount of requests this user has made in the last 24
        hours as well as the maximum allowed by DRF's throttling framework'''
        hits = cache.get('throttle_user_{0}'.format(self.user.id))
        used = len(hits) if hits else 0
        allowed = 'unlimited'  # placeholder in case we ever reimplement a stricter throttle policy
        return {'used': used, 'allowed': allowed}

    @property
    def is_scicollab_admin(self):
        return hasattr(self.user, 'sciencecollaborationallocation')

    def __str__(self):
        return '{0} {1} at {2}'.format(self.user, self.title, self.institution)
