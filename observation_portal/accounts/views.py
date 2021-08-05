from django.utils.functional import empty
from observation_portal.common.mixins import GetSerializerMixin
from observation_portal.accounts.serializers import AcceptTermsSerializer, RevokeTokenSerializer, UserSerializer
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from django.conf import settings
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.response import Response

from observation_portal.accounts.models import Profile
from observation_portal.accounts.tasks import send_mail
from observation_portal.common.schema import ObservationPortalSchema


class ProfileApiView(RetrieveUpdateAPIView):
    schema = ObservationPortalSchema(tags=['Accounts'])
    serializer_class = import_string(settings.SERIALIZERS['accounts']['User'])
    permission_classes = [IsAuthenticated]

    #TODO: Docstrings on get_object are not plumbed into the description for the API endpoint - override this.
    def get_object(self):
        """Once authenticated, retrieve profile data"""
        qs = User.objects.filter(pk=self.request.user.pk).prefetch_related(
            'profile', 'proposal_set', 'proposal_set__timeallocation_set', 'proposalnotification_set'
        )
        return qs.first()


class AcceptTermsApiView(APIView, GetSerializerMixin):
    permission_classes = [IsAuthenticated]
    schema=ObservationPortalSchema(tags=['Accounts'], empty_request=True)
    serializer_class = import_string(settings.SERIALIZERS['accounts']['AcceptTerms'])

    def post(self, request):
        """A simple POST request (empty request body) with user authentication information in the HTTP header will accept the terms of use for the Observation Portal."""
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user, institution='', title='')

        profile.terms_accepted = timezone.now()
        profile.save()
        return Response(self.serializer_class({'message': 'Terms accepted'}).data)


class RevokeApiTokenApiView(APIView, GetSerializerMixin):
    """View to revoke an API token."""
    permission_classes = [IsAuthenticated]
    schema=ObservationPortalSchema(tags=['Accounts'], empty_request=True)
    serializer_class = import_string(settings.SERIALIZERS['accounts']['RevokeToken'])

    def post(self, request):
        """A simple POST request (empty request body) with user authentication information in the HTTP header will revoke a user's API Token."""
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        return Response(self.serializer_class({'message': 'API token revoked.'}).data)


class AccountRemovalRequestApiView(APIView, GetSerializerMixin):
    """View to request account removal."""
    permission_classes = [IsAuthenticated]
    serializer_class = import_string(settings.SERIALIZERS['accounts']['AccountRemovalRequest'])
    schema=ObservationPortalSchema(tags=['Accounts'])

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            message = 'User {0} would like their account removed.\nReason:\n {1}'.format(
                request.user.email, serializer.validated_data['reason']
            )
            send_mail.send(
                'Account removal request submitted', message, settings.ORGANIZATION_EMAIL, [settings.ORGANIZATION_SUPPORT_EMAIL]
            )
            return Response(self.serializer_class({'message': 'Account removal request successfully submitted.'}).data)
        else:
            return Response(serializer.errors, status=400)
