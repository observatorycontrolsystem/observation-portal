import django_filters
from django import forms
from dateutil import parser

from observation_portal.observations.models import Observation, ConfigurationStatus
from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.common.configdb import configdb


class ObservationFilter(django_filters.FilterSet):
    site = django_filters.MultipleChoiceFilter(choices=configdb.get_site_tuples())
    enclosure = django_filters.MultipleChoiceFilter(choices=configdb.get_enclosure_tuples())
    telescope = django_filters.MultipleChoiceFilter(choices=configdb.get_telescope_tuples())
    start_after = django_filters.CharFilter(field_name='start', method='filter_start_after', label='Start after',
                                            widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    start_before = django_filters.CharFilter(field_name='start', method='filter_start_before', label='Start before',
                                             widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    end_after = django_filters.CharFilter(field_name='end', method='filter_end_after', label='End after',
                                          widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    end_before = django_filters.CharFilter(field_name='end', method='filter_end_before', label='End before',
                                           widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    modified_after = django_filters.CharFilter(field_name='modified', method='filter_modified_after',
                                               label='Modified After',
                                               widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    request_id = django_filters.CharFilter(field_name='request__id', method='filter_request_id',
                                            widget=forms.TextInput(attrs={'class': 'input'}))
    request_group_id = django_filters.CharFilter(field_name='request__request_group__id',
                                                 method='filter_request_group_id',
                                                 widget=forms.TextInput(attrs={'class': 'input'}))
    state = django_filters.MultipleChoiceFilter(choices=Observation.STATE_CHOICES)
    exclude_observation_type = django_filters.MultipleChoiceFilter(choices=RequestGroup.OBSERVATION_TYPES,
                                                                   field_name='request__request_group__observation_type',
                                                                   exclude=True)
    observation_type = django_filters.MultipleChoiceFilter(choices=RequestGroup.OBSERVATION_TYPES,
                                                           field_name='request__request_group__observation_type')
    request_state = django_filters.MultipleChoiceFilter(choices=Request.STATE_CHOICES, field_name='request__state')
    proposal = django_filters.CharFilter(field_name='request__request_group__proposal__id', label='Proposal')
    instrument_type = django_filters.CharFilter(
        label='Instrument type',
        field_name='configuration_statuses__configuration__instrument_type'
    )
    ordering = django_filters.OrderingFilter(
        fields=['start', 'end', 'modified', 'created', 'state']
    )

    class Meta:
        model = Observation
        exclude = ['start', 'end']

    def filter_start_after(self, queryset, name, value):
        start = parser.parse(value, ignoretz=True)
        return queryset.filter(start__gte=start)

    def filter_start_before(self, queryset, name, value):
        start = parser.parse(value, ignoretz=True)
        return queryset.filter(start__lt=start)

    def filter_end_after(self, queryset, name, value):
        end = parser.parse(value, ignoretz=True)
        return queryset.filter(end__gte=end)

    def filter_end_before(self, queryset, name, value):
        end = parser.parse(value, ignoretz=True)
        return queryset.filter(end__lt=end)

    def filter_modified_after(self, queryset, name, value):
        modified_after = parser.parse(value, ignoretz=True)
        return queryset.filter(modified__gte=modified_after)

    def filter_request_id(self, queryset, name, value):
        return queryset.filter(request__id=value.zfill(10)).distinct()

    def filter_request_group_id(self, queryset, name, value):
        return queryset.filter(request__request_group__id=value.zfill(10)).distinct()


class ConfigurationStatusFilter(django_filters.FilterSet):
    instrument_name = django_filters.ChoiceFilter(choices=configdb.get_instrument_name_tuples())
    state = django_filters.MultipleChoiceFilter(choices=ConfigurationStatus.STATE_CHOICES)

    class Meta:
        model = ConfigurationStatus
        fields = '__all__'
