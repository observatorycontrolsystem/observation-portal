from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from django.conf import settings
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from observation_portal.accounts.models import Profile
from observation_portal.accounts.tasks import send_mail
from observation_portal.common.schema import ObservationPortalSchema
from observation_portal.common.mixins import GetSerializerMixin


class ProfileApiView(RetrieveUpdateAPIView):
    serializer_class = import_string(settings.SERIALIZERS['accounts']['User'])
    schema = ObservationPortalSchema(tags=['Accounts'])
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
        serializer = self.serializer_class(data={'message': 'Terms accepted'})
        if serializer.is_valid():
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_endpoint_name(self):
        return 'acceptTerms'


class RevokeApiTokenApiView(APIView, GetSerializerMixin):
    """View to revoke an API token."""
    permission_classes = [IsAuthenticated]
    schema = ObservationPortalSchema(tags=['Accounts'], empty_request=True)
    serializer_class = import_string(settings.SERIALIZERS['accounts']['RevokeToken'])

    def post(self, request):
        """A simple POST request (empty request body) with user authentication information in the HTTP header will revoke a user's API Token."""
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        serializer = self.serializer_class(data={'message': 'API token revoked.'})
        if serializer.is_valid():
            return Response(serializer.validated_data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_endpoint_name(self):
        return 'revokeApiToken'


class AccountRemovalRequestApiView(APIView):
    """View to request account removal."""
    permission_classes = [IsAuthenticated]
    schema = ObservationPortalSchema(tags=['Accounts'])

    def post(self, request):
        request_serializer = self.get_request_serializer(data=request.data)
        if request_serializer.is_valid():
            message = 'User {0} would like their account removed.\nReason:\n {1}'.format(
                request.user.email, request_serializer.validated_data['reason']
            )
            send_mail.send(
                'Account removal request submitted', message, settings.ORGANIZATION_EMAIL, [settings.ORGANIZATION_SUPPORT_EMAIL]
            )
            response_serializer = self.get_response_serializer(data={'message': 'Account removal request successfully submitted.'})
            if response_serializer.is_valid():
                return Response(response_serializer.validated_data)
            else:
                return Response(response_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_request_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['AccountRemovalRequest'])(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['AccountRemovalResponse'])(*args, **kwargs)

    def get_endpoint_name(self):
        return 'requestAccountRemoval'
