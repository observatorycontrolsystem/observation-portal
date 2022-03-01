from django.urls import re_path, include
from django.views.generic.base import TemplateView
from registration.backends.default.views import RegistrationView

from observation_portal.accounts.forms import CustomRegistrationForm

urlpatterns = [
    re_path(r'^register/$', RegistrationView.as_view(form_class=CustomRegistrationForm), name='registration_register'),
    re_path(r'^loggedinstate/$', TemplateView.as_view(template_name='auth/logged_in_state.html'), name='logged-in-state'),
    re_path(r'', include('registration.backends.default.urls')),
]
