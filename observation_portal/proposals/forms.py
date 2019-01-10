from django import forms


class ProposalNotificationForm(forms.Form):
    notifications_enabled = forms.BooleanField(required=False)
