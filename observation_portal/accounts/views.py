from django.urls import reverse_lazy
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic.edit import FormView

from observation_portal.accounts.forms import AccountRemovalForm
from observation_portal.accounts.serializers import UserSerializer


class ProfileApiView(RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        if self.request.user.is_authenticated:
            return self.request.user
        else:
            return None


class RevokeApiTokenApiView(APIView):
    """
    View to revoke an API token.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        return Response({'message': 'API token revoked.'})


class AccountRemovalRequestView(LoginRequiredMixin, FormView):
    template_name = 'auth/account_removal.html'
    form_class = AccountRemovalForm
    success_url = reverse_lazy('profile')

    def form_valid(self, form):
        form.send_email(self.request.user)
        messages.success(self.request, 'Account removal request successfully submitted')
        return super().form_valid(form)
