from django.urls import re_path, include, path
from django.views.generic.base import TemplateView

from observation_portal.accounts.views import CustomRegistrationView
from observation_portal.accounts.forms import CustomRegistrationForm

from .views import (
    CustomLoginView,
    CustomPasswordChangeView,
    CustomPasswordResetConfirmView,
)

urlpatterns = [
    re_path(r'^register/$', CustomRegistrationView.as_view(form_class=CustomRegistrationForm), name='registration_register'),
    re_path(r'^loggedinstate/$', TemplateView.as_view(template_name='auth/logged_in_state.html'), name='logged-in-state'),
    path("login/", CustomLoginView.as_view(), name="auth_login"),
    path("password/change/", CustomPasswordChangeView.as_view(), name="auth_password_change"),
    path("password/reset/confirm/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view(), name="auth_password_reset_confirm"),
    re_path(r'', include('registration.backends.default.urls')),
]
