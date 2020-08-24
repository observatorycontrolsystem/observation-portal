import django_filters
from observation_portal.requestgroups.models import RequestGroup, Request


class RequestGroupFilter(django_filters.FilterSet):
    created_after = django_filters.DateTimeFilter(field_name='created', lookup_expr='gte', label='Submitted after')
    created_before = django_filters.DateTimeFilter(field_name='created', lookup_expr='lte', label='Submitted before')
    name = django_filters.CharFilter(field_name='name', lookup_expr='icontains', label='Name contains')
    state = django_filters.ChoiceFilter(choices=RequestGroup.STATE_CHOICES)
    user = django_filters.CharFilter(field_name='submitter__username', lookup_expr='icontains', label='Username contains')
    exclude_state = django_filters.ChoiceFilter(field_name='state', choices=RequestGroup.STATE_CHOICES, label='Exclude State', exclude=True)
    # TODO: Fill in telescope_class choices from configdb
    # telescope_class = django_filters.ChoiceFilter(
    #     choices=Location.TELESCOPE_CLASSES, field_name='requests__location__telescope_class', distinct=True,
    # )
    target = django_filters.CharFilter(
        field_name='requests__configurations__target__name', lookup_expr='icontains', label='Target name contains',
        distinct=True
    )
    modified_after = django_filters.DateTimeFilter(field_name='requests__modified', lookup_expr='gte', label='Modified After', distinct=True)
    modified_before = django_filters.DateTimeFilter(field_name='requests__modified', lookup_expr='lte', label='Modified Before', distinct=True)
    order = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('modified', 'modified'),
            ('created', 'created'),
            ('requests__windows__end', 'end')
        ),
        field_labels={
            'requests__windows__end': 'End of window',
            'modified': 'Last Update'
        }
    )
    request_id = django_filters.NumberFilter(field_name='requests__id')

    class Meta:
        model = RequestGroup
        fields = (
            'id', 'submitter', 'proposal', 'name', 'observation_type', 'operator', 'ipp_value',  'exclude_state',
            'state', 'created_after', 'created_before', 'user', 'modified_after', 'modified_before', 'request_id'
        )


class RequestFilter(django_filters.FilterSet):
    class Meta:
        model = Request
        fields = ('state',)
