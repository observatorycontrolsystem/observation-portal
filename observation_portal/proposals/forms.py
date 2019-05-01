from django import forms
from observation_portal.common.configdb import configdb
from observation_portal.proposals.models import TimeAllocation


class ProposalNotificationForm(forms.Form):
    notifications_enabled = forms.BooleanField(required=False)


class TimeAllocationForm(forms.ModelForm):
    class Meta:
        model = TimeAllocation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['instrument_type'] = forms.ChoiceField(choices=configdb.get_instrument_type_tuples())

