import django_filters
from django import forms

from observation_portal.observations.models import Observation
from observation_portal.common.configdb import configdb


class PondBlockFilter(django_filters.FilterSet):
    site = django_filters.MultipleChoiceFilter(choices=configdb.get_site_tuples())
    observatory = django_filters.MultipleChoiceFilter(choices=configdb.get_enclosure_tuples(), field_name='enclosure')
    telescope = django_filters.MultipleChoiceFilter(choices=configdb.get_telescope_tuples())
    start_after = django_filters.DateTimeFilter(
        field_name='start',
        lookup_expr='gte',
        label='Start after',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    start_before = django_filters.DateTimeFilter(
        field_name='start',
        lookup_expr='lt',
        label='Start before',
        widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'})
    )
    end_after = django_filters.DateTimeFilter(field_name='end', lookup_expr='gte', label='End after')
    end_before = django_filters.DateTimeFilter(field_name='end', lookup_expr='lt', label='End before')
    modified_after = django_filters.DateTimeFilter(field_name='modified', lookup_expr='gte', label='Modified After')
    request_num = django_filters.CharFilter(field_name='request__id')
    tracking_num = django_filters.CharFilter(field_name='request__request_group__id')
    proposal = django_filters.CharFilter(
        field_name='request__request_group__proposal__id',
        distinct=True,
        lookup_expr='exact'
    )
    instrument_class = django_filters.ChoiceFilter(
        choices=configdb.get_instrument_type_tuples(),
        field_name='configuration_statuses__configuration__instrument_type'
    )
    canceled = django_filters.BooleanFilter(method='filter_canceled')
    order = django_filters.OrderingFilter(fields=('start', 'modified'))
    time_span = django_filters.DateRangeFilter(field_name='start')

    class Meta:
        model = Observation
        exclude = ['start', 'end', 'request', 'created', 'modified']

    def filter_canceled(self, queryset, name, value):
        if not value:
            return queryset.exclude(state='CANCELED')
        else:
            return queryset
