from rest_framework import viewsets, filters
from rest_framework.permissions import IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.observations.models import Observation
from observation_portal.observations.serializers import (ObservationSerializer, ConfigurationStatusSerializer,
                                                         ScheduleSerializer)
from observation_portal.observations.filters import ObservationFilter, ConfigurationStatusFilter

import logging


# from https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
class CreateListModelMixin(object):
    def get_serializer(self, *args, **kwargs):
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)


class ScheduleViewSet(CreateListModelMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = ScheduleSerializer
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
                                   'request__configurations__instrument_configs__rois').distinct()


class ObservationViewSet(CreateListModelMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['post', 'head', 'options']
    serializer_class = ObservationSerializer


class ConfigurationStatusViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['get', 'patch']
    serializer_class = ConfigurationStatusSerializer
    filter_class = ConfigurationStatusFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

