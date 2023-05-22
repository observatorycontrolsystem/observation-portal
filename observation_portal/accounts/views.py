import json
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetConfirmView
from django.utils.module_loading import import_string
from django.conf import settings
from django.urls import reverse_lazy
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from registration.backends.default.views import RegistrationView

from observation_portal.accounts.models import Profile
from observation_portal.accounts.tasks import send_mail, update_or_create_client_applications_user
from observation_portal.common.schema import ObservationPortalSchema

from .permissions import IsPrincipleInvestigatorOfAnyProposal


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


class AcceptTermsApiView(APIView):
    permission_classes = [IsAuthenticated]
    schema=ObservationPortalSchema(tags=['Accounts'], empty_request=True)

    def post(self, request):
        """A simple POST request (empty request body) with user authentication information in the HTTP header will accept the terms of use for the Observation Portal."""
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user, institution='', title='')

        profile.terms_accepted = timezone.now()
        profile.save()
        serializer = self.get_response_serializer({'message': 'Terms accepted'})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_response_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['AcceptTerms'])(*args, **kwargs)

    def get_endpoint_name(self):
        return 'acceptTerms'


class RevokeApiTokenApiView(APIView):
    """View to revoke an API token."""
    permission_classes = [IsAuthenticated]
    schema = ObservationPortalSchema(tags=['Accounts'], empty_request=True)

    def post(self, request):
        """A simple POST request (empty request body) with user authentication information in the HTTP header will revoke a user's API Token."""
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        # The Oauth Client applications must have their api_token updated as well
        user_json = json.dumps(import_string(settings.SERIALIZERS['accounts']['User'])(request.user).data)
        update_or_create_client_applications_user.send(user_json)
        serializer = self.get_response_serializer({'message': 'API token revoked.'})

        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_response_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['RevokeToken'])(*args, **kwargs)

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
            response_serializer = self.get_response_serializer({'message': 'Account removal request successfully submitted.'})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_request_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['AccountRemovalRequest'])(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['accounts']['AccountRemovalResponse'])(*args, **kwargs)

    def get_endpoint_name(self):
        return 'requestAccountRemoval'


class BulkCreateUsersApiView(CreateAPIView):
    """API endpoint to create users in bulk"""

    permission_classes = [IsAdminUser | IsPrincipleInvestigatorOfAnyProposal]
    serializer_class = import_string(settings.SERIALIZERS["accounts"]["BulkCreateUsersSerializer"])
    schema = ObservationPortalSchema(tags=['Accounts'])

    def get_endpoint_name(self):
        return 'createUsersBulk'


class CustomLoginView(LoginView):

    def get_success_url(self):
        u = self.request.user
        if hasattr(u, "profile"):
            exp = u.profile.password_expiration
            if exp is not None and timezone.now() > exp:
                return reverse_lazy("auth_password_change")

        return super().get_success_url()


class ResetPasswordExpirationFormMixin:

    def form_valid(self, form):
        u = form.user
        if hasattr(u, "profile"):
            exp = u.profile.password_expiration
            if exp is not None:
                new_exp = timezone.now() + timedelta(days=365)
                u.profile.password_expiration = new_exp
                u.profile.save(update_fields=["password_expiration"])

        return super().form_valid(form)


class CustomPasswordChangeView(ResetPasswordExpirationFormMixin, PasswordChangeView):
    success_url = reverse_lazy("auth_password_change_done")


class CustomPasswordResetConfirmView(ResetPasswordExpirationFormMixin, PasswordResetConfirmView):
    success_url = reverse_lazy("auth_password_reset_complete")


class CustomRegistrationView(RegistrationView):
    # Pass url parameters from the view to the form
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'email': self.request.GET.get('email')})
        return kwargs
