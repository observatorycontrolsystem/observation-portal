import django_filters
from django import forms

from observation_portal.observations.models import Observation, ConfigurationStatus
from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.common.configdb import configdb
from observation_portal.common import mixins


class ObservationFilter(mixins.CustomIsoDateTimeFilterMixin, django_filters.FilterSet):
    site = django_filters.MultipleChoiceFilter(choices=sorted(configdb.get_site_tuples()))
    enclosure = django_filters.MultipleChoiceFilter(choices=sorted(configdb.get_enclosure_tuples()))
    telescope = django_filters.MultipleChoiceFilter(choices=sorted(configdb.get_telescope_tuples()))
    time_span = django_filters.DateRangeFilter(
        field_name='start',
        label='Time Span'
    )
    start_after = django_filters.IsoDateTimeFilter(
        field_name='start',
        lookup_expr='gte',
        label='Start After (Inclusive)',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    start_before = django_filters.IsoDateTimeFilter(
        field_name='start',
        lookup_expr='lt',
        label='Start Before',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    end_after = django_filters.IsoDateTimeFilter(
        field_name='end',
        lookup_expr='gte',
        label='End After (Inclusive)',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    end_before = django_filters.IsoDateTimeFilter(
        field_name='end',
        lookup_expr='lt',
        label='End Before',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    modified_after = django_filters.IsoDateTimeFilter(
        field_name='modified',
        lookup_expr='gte',
        label='Modified After (Inclusive)',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    request_id = django_filters.NumberFilter(field_name='request__id')
    request_group_id = django_filters.NumberFilter(field_name='request__request_group__id', label='Request Group ID')
    state = django_filters.MultipleChoiceFilter(choices=Observation.STATE_CHOICES, field_name='state')
    observation_type = django_filters.MultipleChoiceFilter(
        choices=RequestGroup.OBSERVATION_TYPES,
        field_name='request__request_group__observation_type',
        label='Observation Type'
    )
    request_state = django_filters.MultipleChoiceFilter(
        choices=Request.STATE_CHOICES,
        field_name='request__state',
        label='Request State'
    )
    proposal = django_filters.CharFilter(field_name='request__request_group__proposal__id', label='Proposal')
    instrument_type = django_filters.MultipleChoiceFilter(
        choices=sorted(configdb.get_instrument_type_tuples()),
        label='Instrument Type',
        field_name='configuration_statuses__configuration__instrument_type'
    )
    configuration_type = django_filters.MultipleChoiceFilter(
        choices=sorted(configdb.get_configuration_type_tuples()),
        label='Configuration Type',
        field_name='configuration_statuses__configuration__type'
    )
    ordering = django_filters.OrderingFilter(
        fields=['start', 'end', 'modified', 'created', 'state']
    )

    class Meta:
        model = Observation
        exclude = ['start', 'end', 'request', 'created', 'modified']


class ConfigurationStatusFilter(django_filters.FilterSet):
    instrument_name = django_filters.ChoiceFilter(choices=configdb.get_instrument_name_tuples())
    state = django_filters.MultipleChoiceFilter(choices=ConfigurationStatus.STATE_CHOICES)
    site = django_filters.ChoiceFilter(choices=configdb.get_site_tuples(), field_name='observation__site')

    class Meta:
        model = ConfigurationStatus
        fields = ('guide_camera_name',)
