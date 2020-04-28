import django_filters
from observation_portal.requestgroups.models import RequestGroup

TELESCOPE_CLASSES = (
        ('2m0', '2m0'),
        ('1m0', '1m0'),
        ('0m8', '0m8'),
        ('0m4', '0m4'),
    )


class UserRequestFilter(django_filters.FilterSet):
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte', label='Submitted after')
    created_before = django_filters.DateTimeFilter(field_name='created', lookup_expr='lte', label='Submitted before')
    state = django_filters.ChoiceFilter(choices=RequestGroup.STATE_CHOICES)
    title = django_filters.CharFilter(field_name='name', lookup_expr='icontains', label='Title contains')
    user = django_filters.CharFilter(field_name='submitter__username', lookup_expr='icontains',
                                     label='Username contains')
    exclude_state = django_filters.ChoiceFilter(field_name='state', choices=RequestGroup.STATE_CHOICES,
                                                label='Exclude State', exclude=True)
    telescope_class = django_filters.ChoiceFilter(
        choices=TELESCOPE_CLASSES, field_name='requests__location__telescope_class', distinct=True,
    )
    target = django_filters.CharFilter(
        field_name='requests__configurations__target__name', lookup_expr='icontains', label='Target name contains',
        distinct=True
    )
    modified_after = django_filters.DateTimeFilter(field_name='requests__modified', lookup_expr='gte',
                                                   label='Modified After', distinct=True)
    modified_before = django_filters.DateTimeFilter(field_name='requests__modified', lookup_expr='lte',
                                                    label='Modified Before', distinct=True)
    order = django_filters.OrderingFilter(
        label='Ordered By',
        fields=(
            ('name', 'title'),
            ('modified', 'modified'),
            ('created', 'created'),
            ('requests__windows__end', 'end')
        ),
        field_labels={
            'requests__windows__end': 'End of window',
            'modified': 'Last Update'
        }
    )

    class Meta:
        model = RequestGroup
        fields = (
            'id', 'submitter', 'proposal', 'name', 'observation_type', 'operator', 'ipp_value',  'exclude_state',
            'state', 'created_after', 'created_before', 'user', 'modified_after', 'modified_before'
        )
