import django_filters
from django import forms
from dateutil import parser
from distutils.util import strtobool

from observation_portal.observations.models import Observation
from observation_portal.common.configdb import configdb


class PondBlockFilter(django_filters.FilterSet):
    site = django_filters.MultipleChoiceFilter(choices=configdb.get_site_tuples())
    observatory = django_filters.MultipleChoiceFilter(choices=configdb.get_enclosure_tuples())
    telescope = django_filters.MultipleChoiceFilter(choices=configdb.get_telescope_tuples())
    start_after = django_filters.CharFilter(field_name='start', method='filter_start_after', label='Start after',
                                            widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    start_before = django_filters.CharFilter(field_name='start', method='filter_start_before', label='Start before',
                                             widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    end_after = django_filters.CharFilter(field_name='end', method='filter_end_after', label='End after')
    end_before = django_filters.CharFilter(field_name='end', method='filter_end_before', label='End before')
    modified_after = django_filters.CharFilter(field_name='modified', method='filter_modified_after',
                                               label='Modified After')
    request_num = django_filters.CharFilter(field_name='request__id')
    tracking_num = django_filters.CharFilter(field_name='request__request_group__id')
    proposal = django_filters.CharFilter(field_name='request__request_group__proposal__id', distinct=True, lookup_expr='exact')
    instrument_class = django_filters.ChoiceFilter(choices=configdb.get_instrument_type_tuples(),
                                                   field_name='configuration_statuses__configuration__instrument_type')
    canceled = django_filters.TypedChoiceFilter(choices=(('false', 'False'), ('true', 'True')),
                                                method='filter_canceled', coerce=strtobool)
    order = django_filters.OrderingFilter(fields=('start', 'modified'))
    time_span = django_filters.DateRangeFilter(field_name='start')

    class Meta:
        model = Observation
        exclude = ['start', 'end', 'request', 'created', 'modified']

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

    def filter_canceled(self, queryset, name, value):
        if not value:
            return queryset.exclude(state='CANCELED')
        else:
            return queryset