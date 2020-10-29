import django_filters

from observation_portal.sciapplications.models import ScienceApplication


class ScienceApplicationFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=ScienceApplication.STATUS_CHOICES
    )
    exclude_status = django_filters.ChoiceFilter(
        choices=ScienceApplication.STATUS_CHOICES, exclude=True, field_name='status'
    )

    class Meta:
        model = ScienceApplication
        fields = ('call', 'status', 'exclude_status')
