from django import forms

from observation_portal.common.configdb import configdb
from observation_portal.requestgroups.models import Location


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'] = forms.ChoiceField(choices=configdb.get_site_tuples(include_blank=True))
        self.fields['enclosure'] = forms.ChoiceField(choices=configdb.get_enclosure_tuples(include_blank=True))
        self.fields['telescope'] = forms.ChoiceField(choices=configdb.get_telescope_tuples(include_blank=True))
        self.fields['telescope_class'] = forms.ChoiceField(choices=configdb.get_telescope_class_tuples())
