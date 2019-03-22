from django import forms
from django.contrib.auth.models import User
from registration.forms import RegistrationFormTermsOfService, RegistrationFormUniqueEmail

from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import ProposalInvite
from observation_portal.accounts.tasks import send_mail


class CustomRegistrationForm(RegistrationFormTermsOfService, RegistrationFormUniqueEmail):
    username = forms.CharField(max_length=50)
    first_name = forms.CharField(max_length=200)
    last_name = forms.CharField(max_length=200)
    institution = forms.CharField(max_length=200)
    title = forms.CharField(max_length=200)
    education_user = forms.BooleanField(required=False)

    field_order = [
        'first_name', 'last_name', 'institution', 'title',
        'email', 'username', 'password1', 'password2', 'education_user', 'tos'
    ]

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        help_texts = {
            'username': 'Will be present under the USERID fits header.',
        }

    def save(self, commit=True):
        new_user_instance = super().save(commit)
        Profile.objects.create(
            user=new_user_instance,
            title=self.cleaned_data['title'],
            institution=self.cleaned_data['institution'],
            education_user=self.cleaned_data['education_user'],
            notifications_enabled=self.cleaned_data['education_user'],
            notifications_on_authored_only=self.cleaned_data['education_user'],
            view_authored_requests_only=self.cleaned_data['education_user'],
            simple_interface=self.cleaned_data['education_user']
        )
        for invite in ProposalInvite.objects.filter(email__iexact=new_user_instance.email):
            invite.accept(new_user_instance)

        return new_user_instance


class UserForm(forms.ModelForm):
    username = forms.CharField(max_length=50)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']

    def clean_email(self):
        email = self.cleaned_data['email']
        if email and User.objects.filter(email=email).exclude(pk=self.instance.id).exists():
            raise forms.ValidationError('User with this email already exists')
        return email


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.user.is_staff:
            self.fields.pop('staff_view')

    class Meta:
        model = Profile
        fields = [
            'institution', 'title', 'simple_interface', 'notifications_enabled',
            'notifications_on_authored_only', 'view_authored_requests_only', 'staff_view'
        ]
        help_texts = {
            'notifications_enabled': (
                'Recieve email notifications for every completed observation on all proposals. '
                'To recieve email notifications for a single proposal, update your preferences '
                'on that proposal\'s detail page.'
            ),
            'simple_interface': 'Hide advanced fields on the request composition page.',
            'notifications_on_authored_only': (
                'Only recieve email notifications for requests you have submitted yourself. '
                'Note this setting alone does not enable any notifications. You must either '
                'enable the \"Noficiations enabled\" setting above or enable notifications '
                'on a specific proposal for this to take effect.'
            ),
            'view_authored_requests_only': 'Only requests that were authored by you will be visible.',
        }


class AccountRemovalForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea)

    def send_email(self, user):
        message = 'User {0} would like their account removed.\nReason:\n {1}'.format(
            user.email, self.cleaned_data['reason']
        )
        send_mail.send(
           'Account removal request submitted', message, 'portal@lco.global', ['science-support@lco.global']
        )
