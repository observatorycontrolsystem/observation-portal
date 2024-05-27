from django import forms
from django.forms.widgets import SelectMultiple

from observation_portal.common.configdb import configdb
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.proposals.models import TimeAllocation, CollaborationAllocation


class ProposalNotificationForm(forms.Form):
    notifications_enabled = forms.BooleanField(required=False)


class CollaborationAllocationForm(forms.ModelForm):
    class Meta:
        model = CollaborationAllocation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['telescope_name'] = forms.ChoiceField(choices=configdb.get_telescope_name_tuples())


class TimeAllocationForm(forms.ModelForm):
    class Meta:
        model = TimeAllocation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['instrument_types'] = forms.MultipleChoiceField(
            choices=configdb.get_instrument_type_tuples_state_grouped(),
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk is None:
            return
        instrument_types_changed = cleaned_data.get('instrument_types') != self.instance.instrument_types
        semester_changed = cleaned_data.get('semester') != self.instance.semester
        if instrument_types_changed or semester_changed:
            # instrument_type has changed. We should block this if the old instrument_type was in use
            requestgroups = RequestGroup.objects.filter(proposal=self.instance.proposal).prefetch_related(
                'requests', 'requests__windows', 'requests__configurations'
            )
            for requestgroup in requestgroups:
                if requestgroup.observation_type not in RequestGroup.NON_SCHEDULED_TYPES:
                    for request in requestgroup.requests.all():
                        for tak in request.time_allocation_keys:
                            if (tak.instrument_type in self.instance.instrument_types and
                                    tak.semester == self.instance.semester.id):
                                if tak.instrument_type not in cleaned_data.get('instrument_types') or semester_changed:
                                    raise forms.ValidationError("Cannot change TimeAllocation's instrument_type/semester when it is in use")
            # or if one of the new instrument types are in use already in the same semester/proposal
            tas_count = TimeAllocation.objects.exclude(id=self.instance.id).filter(proposal=self.instance.proposal, semester=cleaned_data.get('semester'),
                                                      instrument_types__overlap=cleaned_data.get('instrument_types')).count()
            if tas_count > 0:
                raise forms.ValidationError("The TimeAllocation's combination of semester, proposal and instrument_type must be unique")


class TimeAllocationFormSet(forms.models.BaseInlineFormSet):
    def clean(self):
        super().clean()
        # Need to check if the combination of all cleaned form data results in a uniqueness violation
        instrument_types_by_semester = {}
        for form in self.forms:
            if not form.is_valid():
                return
            if form.cleaned_data:
                semester = form.cleaned_data.get('semester').id
                if semester not in instrument_types_by_semester:
                    instrument_types_by_semester[semester] = set()
                for it in form.cleaned_data.get('instrument_types'):
                    if it in instrument_types_by_semester[semester]:
                        raise forms.ValidationError(f"Multiple TimeAllocations have instrument_type {it} set for the same semester. The combination of semester, proposal and instrument_type must be unique")
                    instrument_types_by_semester[semester].add(it)
            if form.cleaned_data and form.cleaned_data.get('DELETE'):
                requestgroups = RequestGroup.objects.filter(proposal=form.cleaned_data.get('proposal')).prefetch_related(
                    'requests', 'requests__windows', 'requests__configurations'
                )
                for requestgroup in requestgroups:
                    if requestgroup.observation_type not in RequestGroup.NON_SCHEDULED_TYPES:
                        for request in requestgroup.requests.all():
                            for tak in request.time_allocation_keys:
                                if (tak.instrument_type in form.cleaned_data.get('instrument_types') and
                                        tak.semester == form.cleaned_data.get('semester').id):
                                    raise forms.ValidationError('Cannot delete TimeAllocation when it is in use')
