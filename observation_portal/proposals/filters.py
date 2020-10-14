import django_filters
from django.utils import timezone
from dateutil.parser import parse
from observation_portal.proposals.models import Semester, Proposal, Membership, ProposalInvite


class MembershipFilter(django_filters.FilterSet):
    first_name = django_filters.CharFilter(field_name='user__first_name', lookup_expr='icontains', label='First name contains')
    last_name = django_filters.CharFilter(field_name='user__last_name', lookup_expr='icontains', label='Last name contains')
    username = django_filters.CharFilter(field_name='user__username', lookup_expr='icontains', label='UserId contains')
    email = django_filters.CharFilter(field_name='user__email', lookup_expr='icontains', label='Email contains')

    class Meta:
        model = Membership
        fields = ('first_name', 'last_name', 'username', 'email', 'proposal', 'role')


class ProposalFilter(django_filters.FilterSet):
    semester = django_filters.ModelChoiceFilter(
        label="Semester", distinct=True, queryset=Semester.objects.all().order_by('-start')
    )
    active = django_filters.ChoiceFilter(choices=((False, 'Inactive'), (True, 'Active')), empty_label='All')

    class Meta:
        model = Proposal
        fields = ('active', 'semester', 'id', 'tac_rank', 'tac_priority', 'public', 'title')


class SemesterFilter(django_filters.FilterSet):
    semester_contains = django_filters.CharFilter(method='semester_contains_filter', label='Contains Date')
    start = django_filters.DateTimeFilter(field_name='start', lookup_expr='gte')
    start_lte = django_filters.DateTimeFilter(field_name='start', lookup_expr='lte')
    end = django_filters.DateTimeFilter(field_name='end', lookup_expr='lt')
    end_gt = django_filters.DateTimeFilter(field_name='end', lookup_expr='gt')
    id = django_filters.CharFilter(field_name='id', lookup_expr='icontains')

    def semester_contains_filter(self, queryset, name, value):
        try:
            date_value = parse(value)
            date_value = date_value.replace(tzinfo=timezone.utc)
            return queryset.filter(start__lte=date_value, end__gte=date_value)
        except ValueError:
            return queryset

    class Meta:
        model = Semester
        fields = ['semester_contains', 'start', 'end', 'id']


class ProposalInviteFilter(django_filters.FilterSet):
    pending = django_filters.BooleanFilter(method='pending_invitations')

    class Meta:
        model = ProposalInvite
        fields = ['proposal']

    def pending_invitations(self, queryset, name, value):
        if value:
            return queryset.filter(used=None)
        else:
            return queryset.exclude(used=None)
