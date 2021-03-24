from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from django.conf import settings
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response

from observation_portal.accounts.models import Profile
from observation_portal.accounts.tasks import send_mail


class ProfileApiView(RetrieveUpdateAPIView):
    serializer_class = import_string(settings.SERIALIZERS['accounts']['User'])
    permission_classes = [IsAuthenticated]

    def get_object(self):
        qs = User.objects.filter(pk=self.request.user.pk).prefetch_related(
            'profile', 'proposal_set', 'proposal_set__timeallocation_set', 'proposalnotification_set'
        )
        return qs.first()


class AcceptTermsApiView(APIView):
    """View to accept terms."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user, institution='', title='')

        profile.terms_accepted = timezone.now()
        profile.save()
        return Response({'message': 'Terms accepted.'})


class RevokeApiTokenApiView(APIView):
    """View to revoke an API token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        return Response({'message': 'API token revoked.'})


class AccountRemovalRequestApiView(APIView):
    """View to request account removal."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = import_string(settings.SERIALIZERS['accounts']['AccountRemoval'])(data=request.data)
        if serializer.is_valid():
            message = 'User {0} would like their account removed.\nReason:\n {1}'.format(
                request.user.email, serializer.validated_data['reason']
            )
            send_mail.send(
                'Account removal request submitted', message, settings.ORGANIZATION_EMAIL, [settings.ORGANIZATION_SUPPORT_EMAIL]
            )
            return Response({'message': 'Account removal request successfully submitted.'})
        else:
            return Response(serializer.errors, status=400)
