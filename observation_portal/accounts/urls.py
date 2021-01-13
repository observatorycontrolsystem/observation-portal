from django.conf.urls import url, include
from django.views.generic.base import TemplateView
from registration.backends.default.views import RegistrationView

from observation_portal.accounts.forms import CustomRegistrationForm

urlpatterns = [
    url(r'^register/$', RegistrationView.as_view(form_class=CustomRegistrationForm), name='registration_register'),
    url(r'^loggedinstate/$', TemplateView.as_view(template_name='auth/logged_in_state.html'), name='logged-in-state'),
    url(r'', include('registration.backends.default.urls')),
]
