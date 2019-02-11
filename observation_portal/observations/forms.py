from django import forms

from observation_portal.common.configdb import configdb
from observation_portal.observations.models import Observation


class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'] = forms.ChoiceField(choices=configdb.get_site_tuples())
        self.fields['enclosure'] = forms.ChoiceField(choices=configdb.get_enclosure_tuples())
        self.fields['telescope'] = forms.ChoiceField(choices=configdb.get_telescope_tuples())
