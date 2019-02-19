from rest_framework import viewsets, filters
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.requestgroups.models import RequestGroup
from observation_portal.observations.models import Observation
from observation_portal.observations.serializers import (ObservationSerializer, ConfigurationStatusSerializer,
                                                         ScheduleSerializer, CancelObservationsSerializer)
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

    def get_queryset(self):
        qs = Observation.objects.all()
        return qs.prefetch_related('request', 'request__request_group').distinct()

    @action(detail=False, methods=['post'])
    def cancel(self, request):
        cancel_serializer = CancelObservationsSerializer(data=request.data)
        if cancel_serializer.is_valid():
            observations = self.get_queryset()
            if 'ids' in cancel_serializer.data:
                observations = observations.filter(pk__in=cancel_serializer.data['ids'])

            if 'start' in cancel_serializer.data:
                observations = observations.filter(end__gt=cancel_serializer.data['start'])
            if 'end' in cancel_serializer.data:
                observations = observations.filter(start__lt=cancel_serializer.data['end'])
            if 'site' in cancel_serializer.data:
                observations = observations.filter(site=cancel_serializer.data['site'])
            if 'enclosure' in cancel_serializer.data:
                observations = observations.filter(enclosure=cancel_serializer.data['enclosure'])
            if 'telescope' in cancel_serializer.data:
                observations = observations.filter(telescope=cancel_serializer.data['telescope'])
            if not cancel_serializer.data.get('include_rr', False):
                observations = observations.exclude(
                    request__request_group__observation_type=RequestGroup.RAPID_RESPONSE)
            if not cancel_serializer.data.get('include_direct', False):
                observations = observations.exclude(request__request_group__observation_type=RequestGroup.DIRECT)
            observations = observations.filter(state__in=['PENDING', 'IN_PROGRESS'])
            # Receive a list of observation id's to cancel
            num_canceled = Observation.cancel(observations)

            return Response({'canceled': num_canceled}, status=200)
        else:
            return Response(cancel_serializer.errors, status=400)


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

