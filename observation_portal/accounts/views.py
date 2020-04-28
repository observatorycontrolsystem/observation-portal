from django.views.generic.base import TemplateView, View
from django.urls import reverse, reverse_lazy
from rest_framework.generics import RetrieveAPIView
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.schemas.openapi import AutoSchema
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import ugettext as _
from django.utils import timezone
from django.shortcuts import redirect
from django.contrib import messages
from django.views.generic.edit import FormView

from observation_portal.accounts.forms import UserForm, ProfileForm, AccountRemovalForm, AcceptTermsForm
from observation_portal.accounts.serializers import UserSerializer


class MyAuthTokenView(ObtainAuthToken):
    schema = AutoSchema(tags=['Users API'])


class UserUpdateView(LoginRequiredMixin, TemplateView):
    template_name = 'auth/user_form.html'

    def get(self, request):
        context = self.get_context_data(
            user_form=UserForm(instance=self.request.user),
            profile_form=ProfileForm(instance=self.request.user.profile)
        )
        return super().render_to_response(context)

    def post(self, request):
        user_form = UserForm(request.POST, instance=request.user)
        profile_form = ProfileForm(request.POST, instance=request.user.profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, _('Profile successfully updated'))
            return redirect('requestgroups:list')
        else:
            context = self.get_context_data(user_form=user_form, profile_form=profile_form)
            return super().render_to_response(context)


class ProfileApiView(RetrieveAPIView):
    schema = AutoSchema(tags=['Users API'])
    serializer_class = UserSerializer

    def get_object(self):
        if self.request.user.is_authenticated:
            return self.request.user
        else:
            return None


class RevokeAPITokenView(LoginRequiredMixin, View):
    def post(self, request):
        request.user.auth_token.delete()
        Token.objects.create(user=request.user)
        messages.success(request, 'API token revoked.')
        return redirect(reverse('profile'))


class AccountRemovalRequestView(LoginRequiredMixin, FormView):
    template_name = 'auth/account_removal.html'
    form_class = AccountRemovalForm
    success_url = reverse_lazy('profile')

    def form_valid(self, form):
        form.send_email(self.request.user)
        messages.success(self.request, 'Account removal request successfully submitted')
        return super().form_valid(form)


class AcceptTermsView(LoginRequiredMixin, FormView):
    template_name = 'auth/accept_terms.html'
    form_class = AcceptTermsForm
    success_url = reverse_lazy('requestgroups:list')

    def form_valid(self, form):
        self.request.user.profile.terms_accepted = timezone.now()
        self.request.user.profile.save()
        return super().form_valid(form)
