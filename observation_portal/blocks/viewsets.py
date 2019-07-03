from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponseNotAllowed
import logging

from observation_portal.observations.models import Observation
from observation_portal.blocks.filters import PondBlockFilter
from observation_portal.blocks.conversion import (
    convert_pond_blocks_to_observations, convert_observations_to_pond_blocks, PondBlockError
)
from observation_portal.observations.serializers import ScheduleSerializer
from observation_portal.common.mixins import ListAsDictMixin

logger = logging.getLogger(__name__)


class PondBlockViewSet(ListAsDictMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = ScheduleSerializer
    filter_class = PondBlockFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def get_queryset(self):
        qs = Observation.objects.none()
        if self.request.user.is_staff:
            qs = Observation.objects.all()
        return qs.prefetch_related(
            'request', 'request__windows', 'request__configurations', 'request__location',
            'request__configurations__instrument_configs', 'request__configurations__target',
            'request__configurations__acquisition_config',
            'request__configurations__guiding_config', 'request__configurations__constraints',
            'request__configurations__instrument_configs__rois', 'configuration_statuses',
            'configuration_statuses__summary', 'request__request_group', 'request__request_group__proposal'
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user, submitter_id=self.request.user.id)

    def create(self, request, *args, **kwargs):
        try:
            observations = convert_pond_blocks_to_observations(request.data)
        except PondBlockError as e:
            return Response({'error': str(e)}, 400)
        request._full_data = observations
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response_data = response.data
        response_data['results'] = convert_observations_to_pond_blocks(response.data['results'])
        return Response(response_data, 200)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        blocks = convert_observations_to_pond_blocks(response.data)
        return Response(blocks, 200)

    @action(detail=False, methods=['post'])
    def cancel(self, request):
        return HttpResponseNotAllowed("Cancel is not allowed on the pond shim. Call it on the /observations endpoint instead")

    @action(detail=True, methods=['get'])
    def convert(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        blocks = convert_observations_to_pond_blocks(response.data)
        observations = convert_pond_blocks_to_observations(blocks)
        return Response(observations, 200)
