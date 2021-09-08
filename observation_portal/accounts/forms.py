from django import forms
from django.contrib.auth.models import User
from registration.forms import RegistrationFormTermsOfService, RegistrationFormUniqueEmail

from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import ProposalInvite


class CustomRegistrationForm(RegistrationFormTermsOfService, RegistrationFormUniqueEmail):
    username = forms.CharField(max_length=50)
    first_name = forms.CharField(max_length=200)
    last_name = forms.CharField(max_length=200)
    institution = forms.CharField(max_length=200)
    title = forms.CharField(max_length=200)
    simple_interface = forms.BooleanField(label="Use Basic Mode", help_text="Hide advanced fields when making an observation request.", required=False)

    field_order = [
        'first_name', 'last_name', 'institution', 'title',
        'email', 'username', 'password1', 'password2', 'simple_interface', 'tos'
    ]

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        help_texts = {
            'username': 'Will be present under the USERID fits header.',
        }

    def save(self, commit=True):
        new_user_instance = super().save(commit=True)
        Profile.objects.create(
            user=new_user_instance,
            title=self.cleaned_data['title'],
            institution=self.cleaned_data['institution'],
            simple_interface=self.cleaned_data['simple_interface']
        )
        # There may be more than one proposal invite for the same proposal for the same user. Use the latest invite
        # that was sent if this is the case.
        proposal_invites = {}
        for proposal_invite in ProposalInvite.objects.filter(email__iexact=new_user_instance.email).order_by('sent'):
            proposal_invites[proposal_invite.proposal.id] = proposal_invite

        for proposal_id in proposal_invites:
            proposal_invites[proposal_id].accept(new_user_instance)

        return new_user_instance
