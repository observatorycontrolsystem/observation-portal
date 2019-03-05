from django_filters.views import FilterView
from django.views.generic import DetailView

from observation_portal.observations.models import Observation
from observation_portal.common.mixins import StaffRequiredMixin
from observation_portal.observations.filters import ObservationFilter


class ObservationDetailView(StaffRequiredMixin, DetailView):
    model = Observation


class ObservationListView(StaffRequiredMixin, FilterView):
    model = Observation
    filterset_class = ObservationFilter
    paginate_by = 50
    ordering = '-modified'
    template_name = 'observations/observation_list.html'
