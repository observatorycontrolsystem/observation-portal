from django.conf.urls import url, include
from registration.backends.default.views import RegistrationView

from observation_portal.accounts.forms import CustomRegistrationForm
from observation_portal.accounts.views import UserUpdateView, RevokeAPITokenView, AccountRemovalRequestView

urlpatterns = [
    url(r'^register/$', RegistrationView.as_view(form_class=CustomRegistrationForm), name='registration_register'),
    url(r'^profile/$', UserUpdateView.as_view(), name='profile'),
    url(r'^revoketoken/$', RevokeAPITokenView.as_view(), name='revoke-api-token'),
    url(r'^removalrequest/$', AccountRemovalRequestView.as_view(), name='account-removal'),
    url(r'', include('registration.backends.default.urls')),
]
