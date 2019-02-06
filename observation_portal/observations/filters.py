import django_filters
from django import forms
from dateutil import parser

from observation_portal.observations.models import Observation

SITE_CHOICES = (
    ('bpl', 'bpl'),
    ('coj', 'coj'),
    ('cpt', 'cpt'),
    ('elp', 'elp'),
    ('lsc', 'lsc'),
    ('ogg', 'ogg'),
    ('sqa', 'sqa'),
    ('tfn', 'tfn'),
    ('tlv', 'tlv'),
    ('tst', 'tst'),
    ('cit', 'cit')
)

OBSERVATORY_CHOICES = (
    ('aqwa', 'aqwa'),
    ('aqwb', 'aqwb'),
    ('clma', 'clma'),
    ('doma', 'doma'),
    ('domb', 'domb'),
    ('domc', 'domc'),
    ('igla', 'igla')
)

TELESCOPE_CHOICES = (
    ('0m4a', '0m4a'),
    ('0m4b', '0m4b'),
    ('0m4c', '0m4c'),
    ('0m8a', '0m8a'),
    ('1m0a', '1m0a'),
    ('2m0a', '2m0a')
)


class ObservationFilter(django_filters.FilterSet):
    site = django_filters.ChoiceFilter(choices=SITE_CHOICES)
    observatory = django_filters.ChoiceFilter(choices=OBSERVATORY_CHOICES)
    telescope = django_filters.ChoiceFilter(choices=TELESCOPE_CHOICES)
    start_after = django_filters.CharFilter(field_name='start', method='filter_start_after', label='Start after',
                                            widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    start_before = django_filters.CharFilter(field_name='start', method='filter_start_before', label='Start before',
                                             widget=forms.TextInput(attrs={'class': 'input', 'type': 'date'}))
    end_after = django_filters.CharFilter(field_name='end', method='filter_end_after', label='End after')
    end_before = django_filters.CharFilter(field_name='end', method='filter_end_before', label='End before')
    modified_after = django_filters.CharFilter(field_name='modified', method='filter_modified_after',
                                               label='Modified After')
    request_num = django_filters.CharFilter(field_name='request__id', method='filter_request_num',
                                            widget=forms.TextInput(attrs={'class': 'input'}))
    tracking_num = django_filters.CharFilter(field_name='molecules__tracking_num', method='filter_tracking_num', widget=forms.TextInput(attrs={'class': 'input'}))

    class Meta:
        model = Observation
        fields = '__all__'

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

    def filter_request_num(self, queryset, name, value):
        return queryset.filter(request__id=value.zfill(10)).distinct()

    def filter_tracking_num(self, queryset, name, value):
        return queryset.filter(request__request_group__id=value.zfill(10)).distinct()