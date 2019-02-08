from rest_framework import viewsets, filters
from rest_framework.permissions import IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.observations.models import Observation
from observation_portal.observations.serializers import ObservationSerializer
from observation_portal.observations.filters import ObservationFilter

import logging


class ObservationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = ObservationSerializer
    filter_class = ObservationFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user, submitter_id=self.request.user.id)

    def get_queryset(self):
        qs = Observation.objects.all()
        return qs.prefetch_related('request', 'request__configurations', 'request__configurations__instrument_configs',
                                   'request__configurations__target',
                                   'request__configurations__acquisition_config', 'request__request_group',
                                   'request__configurations__guiding_config', 'request__configurations__constraints',
                                   'request__configurations__instrument_configs__rois')

