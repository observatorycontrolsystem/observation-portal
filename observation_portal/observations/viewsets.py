from rest_framework import viewsets, filters
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from django.core.cache import cache
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.requestgroups.models import RequestGroup
from observation_portal.observations.models import Observation, ConfigurationStatus
from observation_portal.observations.serializers import (ObservationSerializer, ConfigurationStatusSerializer,
                                                         ScheduleSerializer, CancelObservationsSerializer)
from observation_portal.observations.filters import ObservationFilter, ConfigurationStatusFilter
from observation_portal.common.mixins import ListAsDictMixin, CreateListModelMixin
from observation_portal.accounts.permissions import IsAdminOrReadOnly, IsDirectUser


def observations_queryset(request):
    if request.user.is_authenticated:
        if request.user.profile.staff_view and request.user.is_staff:
            qs = Observation.objects.all()
        else:
            qs = Observation.objects.filter(request__request_group__proposal__in=request.user.proposal_set.all())
            if request.user.profile.view_authored_requests_only:
                qs = qs.filter(request__request_group__submitter=request.user)
    else:
        qs = Observation.objects.filter(request__request_group__proposal__public=True)
    return qs.prefetch_related(
        'request', 'request__configurations', 'request__configurations__instrument_configs',
        'request__configurations__target', 'request__request_group__proposal',
        'request__configurations__acquisition_config', 'request__request_group',
        'request__configurations__guiding_config', 'request__configurations__constraints',
        'request__configurations__instrument_configs__rois', 'configuration_statuses',
        'configuration_statuses__summary', 'configuration_statuses__configuration', 'request__request_group__submitter'
    ).distinct()


class ScheduleViewSet(ListAsDictMixin, CreateListModelMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminOrReadOnly | IsDirectUser,)
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
        return observations_queryset(self.request)


class ObservationViewSet(CreateListModelMixin, ListAsDictMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminOrReadOnly | IsDirectUser,)
    http_method_names = ['get', 'post', 'head', 'options', 'patch']
    filter_class = ObservationFilter
    serializer_class = ObservationSerializer
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def get_queryset(self):
        return observations_queryset(self.request).prefetch_related('request__windows', 'request__location').distinct()

    @action(detail=False, methods=['get'])
    def filters(self, request):
        obs_filter_options = {'fields': [], 'choice_fields': []}
        for filter_name, filter_field in self.filter_class.get_filters().items():
            if hasattr(filter_field.field, 'choices'):
                obs_filter_options['choice_fields'].append({
                    'name': filter_name,
                    'options': list(filter_field.field.choices)
                })
            else:
                obs_filter_options['fields'].append(filter_name)
        return Response(obs_filter_options, status=200)

    @action(detail=False, methods=['post'])
    def cancel(self, request):
        """
        Filters a set of observations based on the parameters provided, and then either deletes them if they are
        scheduled >72 hours in the future, cancels them if they are in the future, or aborts them if they are currently
        in progress.
        :param request:
        :return:
        """
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
            if not cancel_serializer.data.get('include_normal', True):
                observations = observations.exclude(
                    request__request_group__observation_type__in=[RequestGroup.TIME_CRITICAL, RequestGroup.NORMAL])
            if not cancel_serializer.data.get('include_rr', False):
                observations = observations.exclude(
                    request__request_group__observation_type=RequestGroup.RAPID_RESPONSE)
            if not cancel_serializer.data.get('include_direct', False):
                observations = observations.exclude(request__request_group__observation_type=RequestGroup.DIRECT)
            if request.user and not request.user.is_staff:
                observations = observations.filter(request__request_group__proposal__direct_submission=True)
            observations = observations.filter(state__in=['PENDING', 'IN_PROGRESS'])
            # Receive a list of observation id's to cancel
            num_canceled = Observation.cancel(observations)

            return Response({'canceled': num_canceled}, status=200)
        else:
            return Response(cancel_serializer.errors, status=400)

    def create(self, request, *args, **kwargs):
        """ This overrides the create mixin create method, but does the same thing minus the serializing of the
            data into the response at the end
        """
        cache_key = 'observation_portal_last_schedule_time'
        if not isinstance(request.data, list):
            # Just do the default create for the single observation case
            created_obs = super().create(request, args, kwargs)
            site = request.data['site']
            cache.set(cache_key + f"_{site}", timezone.now(), None)
            return created_obs
        else:
            serializer = self.get_serializer(data=request.data)
            errors = {}
            try:
                serializer.is_valid(raise_exception=True)
                observations = serializer.save()
            except ValidationError:
                # fall back to individually serializing and saving requests if there are any with errors
                observations = []
                for i, error in enumerate(serializer.errors):
                    if error:
                        errors[i] = error
                    else:
                        individual_serializer = self.get_serializer(data=serializer.initial_data[i])
                        if individual_serializer.is_valid():
                            observations.append(individual_serializer.save())
                        else:
                            errors[i] = individual_serializer.error
            site = request.data[0]['site']
            cache.set(cache_key + f"_{site}", timezone.now(), None)
            return Response({'num_created': len(observations), 'errors': errors}, status=201)


class ConfigurationStatusViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['get', 'patch']
    serializer_class = ConfigurationStatusSerializer
    filter_class = ConfigurationStatusFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    queryset = ConfigurationStatus.objects.all().prefetch_related('summary')
    ordering = ('-id',)
