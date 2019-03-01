from django_filters.views import FilterView
from django.views.generic import DetailView
from django_filters.filterset import FilterSet
from django_filters import filters

from observation_portal.observations.models import Observation


class ObservationDetailView(DetailView):
    model = Observation


class ObservationFilter(FilterSet):
    ordering = filters.OrderingFilter(
        fields=['start', 'end', 'modified', 'created', 'state']
    )

    class Meta:
        model = Observation
        exclude = ['request']


class ObservationListView(FilterView):
    model = Observation
    filterset_class = ObservationFilter
    paginate_by = 50
    ordering = '-modified'
    template_name = 'observations/observation_list.html'
