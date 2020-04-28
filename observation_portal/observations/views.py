from datetime import timedelta

from django_filters.views import FilterView
from django.views.generic import DetailView
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.schemas.openapi import AutoSchema
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response

from observation_portal.observations.models import Observation
from observation_portal.common.configdb import configdb
from observation_portal.observations.filters import ObservationFilter
from observation_portal.observations.viewsets import observations_queryset


class ObservationDetailView(DetailView):
    model = Observation

    def get_queryset(self):
        return observations_queryset(self.request)


class ObservationListView(FilterView):
    model = Observation
    filterset_class = ObservationFilter
    paginate_by = 50
    template_name = 'observations/observation_list.html'

    def get_queryset(self):
        return observations_queryset(self.request).order_by('-start')

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super(ObservationListView, self).get_filterset_kwargs(filterset_class)
        # If there are no query parameters or the only query parameter is for pagination, default to
        # filtering out all canceled observations as generally users coming to the page will want
        # those observations filtered out
        if kwargs['data'] is None or (len(kwargs['data']) == 1 and 'page' in kwargs['data']):
            kwargs['data'] = {
                'state': ['COMPLETED', 'PENDING', 'IN_PROGRESS', 'ABORTED', 'FAILED']
            }
        return kwargs


class LastScheduledView(APIView):
    """
        Returns the datetime of the last time new observations were submitted. This endpoint is expected to be polled
        frequently (~every 5 seconds) to for a client to decide if it needs to pull down the schedule or not.

        We are only updating when observations are submitted, and not when they are cancelled, because a site should
        not really care if the only change was removing things from it's schedule.
    """
    schema = AutoSchema(tags=['Observations API'])
    permission_classes = (IsAdminUser,)

    def get(self, request):
        site = request.query_params.get('site')
        cache_key = 'observation_portal_last_schedule_time'
        if site:
            cache_key += f"_{site}"
            last_schedule_time = cache.get(cache_key, timezone.now() - timedelta(days=7))
        else:
            sites = configdb.get_site_tuples()
            keys = [cache_key + "_" + s[0] for s in sites]
            cache_dict = cache.get_many(keys)
            last_schedule_time = max(list(cache_dict.values()) + [timezone.now() - timedelta(days=7)])

        return Response({'last_schedule_time': last_schedule_time})
