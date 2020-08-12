from django.conf.urls import url, include
from django.views.generic.base import TemplateView
from registration.backends.default.views import RegistrationView

from observation_portal.accounts.forms import CustomRegistrationForm
from observation_portal.accounts.views import (
    RevokeAPITokenView, AccountRemovalRequestView
)

urlpatterns = [
    url(r'^register/$', RegistrationView.as_view(form_class=CustomRegistrationForm), name='registration_register'),
    url(r'^revoketoken/$', RevokeAPITokenView.as_view(), name='revoke-api-token'),
    url(r'^removalrequest/$', AccountRemovalRequestView.as_view(), name='account-removal'),
    url(r'^loggedinstate/$', TemplateView.as_view(template_name='auth/logged_in_state.html'), name='logged-in-state'),
    url(r'', include('registration.backends.default.urls')),
]
