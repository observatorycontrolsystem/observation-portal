from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
import logging

from observation_portal.observations.models import Observation
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.blocks.serializers import CancelSerializer
from observation_portal.blocks.filters import PondBlockFilter
from observation_portal.blocks.conversion import (convert_pond_blocks_to_observations,
                                                convert_observations_to_pond_blocks)
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
        serializer.save(submitter=self.request.user)

    def create(self, request, *args, **kwargs):
        observations = convert_pond_blocks_to_observations(request.data)
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
        cancel_serializer = CancelSerializer(data=request.data)
        if cancel_serializer.is_valid():
            observations = self.get_queryset()
            if 'blocks' in cancel_serializer.data:
                observations = observations.filter(pk__in=cancel_serializer.data['blocks'])
            if 'start' in cancel_serializer.data:
                observations = observations.filter(end__gt=cancel_serializer.data['start'])
            if 'end' in cancel_serializer.data:
                observations = observations.filter(start__lt=cancel_serializer.data['end'])
            if 'site' in cancel_serializer.data:
                observations = observations.filter(site=cancel_serializer.data['site'])
            if 'observatory' in cancel_serializer.data:
                observations = observations.filter(enclosure=cancel_serializer.data['observatory'])
            if 'telescope' in cancel_serializer.data:
                observations = observations.filter(telescope=cancel_serializer.data['telescope'])
            if 'is_too' in cancel_serializer.data:
                if cancel_serializer.data['is_too']:
                    observations = observations.filter(request__request_group__observation_type=RequestGroup.RAPID_RESPONSE)
                else:
                    observations = observations.exclude(request__request_group__observation_type=RequestGroup.RAPID_RESPONSE)
            if not cancel_serializer.data['include_nonscheduled']:
                observations = observations.exclude(request__request_group__observation_type=RequestGroup.DIRECT)
            observations = observations.filter(state__in=['PENDING', 'IN_PROGRESS'])

            num_canceled = Observation.cancel(observations)
            return Response({'canceled': num_canceled})
        else:
            return Response(cancel_serializer.errors)

    @action(detail=True, methods=['get'])
    def convert(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        blocks = convert_observations_to_pond_blocks(response.data)
        observations = convert_pond_blocks_to_observations(blocks)
        return Response(observations, 200)
