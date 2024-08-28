from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.authtoken.models import Token
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.requestgroups.models import RequestGroup
from observation_portal.observations.time_accounting import debit_realtime_time_allocation
from observation_portal.observations.models import Observation, ConfigurationStatus
from observation_portal.observations.filters import ObservationFilter, ConfigurationStatusFilter
from observation_portal.observations.realtime import get_realtime_availability
from observation_portal.common.mixins import ListAsDictMixin, CreateListModelMixin
from observation_portal.accounts.permissions import IsAdminOrReadOnly, IsDirectUser
from observation_portal.common.schema import ObservationPortalSchema
from observation_portal.common.doc_examples import EXAMPLE_RESPONSES
from observation_portal.common.downtimedb import DowntimeDB

import logging

logger = logging.getLogger(__name__)


def get_sites_from_request(request):
    sites = set()
    if isinstance(request.data, list):
        # request could be a list of data or a dict, if its a list we need to get all sites
        for req in request.data:
            sites.add(req['site'])
    else:
        sites.add(request.data['site'])
    return sites


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


class RealTimeViewSet(CreateListModelMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ['get', 'post', 'delete']
    serializer_class = import_string(settings.SERIALIZERS['observations']['RealTime'])
    schema = ObservationPortalSchema(tags=['Observations'])

    def get_queryset(self):
        """ This is just used for the delete endpoint to retrieve an object to delete.
            Staff can delete anything, otherwise a user can only delete their own realtime observation.
        """
        if self.request.user.is_authenticated:
            realtime_obs = Observation.objects.filter(request__request_group__observation_type='REAL_TIME')
            if self.request.user.is_staff:
                return realtime_obs
            else:
                return realtime_obs.filter(request__request_group__submitter=self.request.user)
        return Observation.objects.none()

    def perform_create(self, serializer):
        """ This creates the associated downtime block after the observation is created,
            using its observation id as the downtime reason
        """
        observation = serializer.save(submitter=self.request.user, submitter_id=self.request.user.id)
        # Debit the realtime time allocation hours
        obs_hours = (observation.end - observation.start).total_seconds() / 3600.0
        debit_realtime_time_allocation(observation.site, observation.enclosure, observation.telescope,
                                       observation.request.request_group.proposal, obs_hours)
        # Now create the downtime block in DowntimeDB
        downtime = {
            'site': observation.site,
            'enclosure': observation.enclosure,
            'telescope': observation.telescope,
            'start': observation.start.isoformat(),
            'end': observation.end.isoformat(),
            'reason': str(observation.id)
        }
        try:
            auth_token = Token.objects.get(user=self.request.user)
            headers = {'Authorization': f'Token {auth_token.key}'}
            DowntimeDB.create_downtime_interval(headers=headers, downtime=downtime)
        except Token.DoesNotExist:
            logger.warning("Failed to retrieve token for realtime submission user. This should not happen.")

    def perform_destroy(self, instance):
        """ This destroys the associated downtime and also the associated request and request group
        """
        try:
            auth_token = Token.objects.get(user=self.request.user)
            headers = {'Authorization': f'Token {auth_token.key}'}
            DowntimeDB.delete_downtime_interval(headers=headers, site=instance.site, enclosure=instance.enclosure,
                                                telescope=instance.telescope, observation_id=instance.id)
        except Token.DoesNotExist:
            logger.warning("Failed to retrieve token for realtime deletion user. This should not happen.")

        # Now credit the realtime time back to the time allocation with most hours
        negative_obs_hours = -(instance.end - instance.start).total_seconds() / 3600.0
        debit_realtime_time_allocation(instance.site, instance.enclosure, instance.telescope,
                                       instance.request.request_group.proposal, negative_obs_hours)
        # delete the observation and then request group
        rg = instance.request.request_group
        instance.delete()
        rg.delete()

    def create(self, request, *args, **kwargs):
        """ This sets the last scheduled time on a site when any directly submitted request is submitted for that site
        """
        cache_key = 'observation_portal_last_schedule_time'
        created_obs = super().create(request, args, kwargs)
        sites = get_sites_from_request(request)
        for site in sites:
            cache.set(f"{cache_key}_{site}", timezone.now(), None)
        return created_obs

    @method_decorator(cache_page(60 * 5))
    @action(detail=False, methods=['get'], permission_classes=(IsAuthenticated,))
    def availability(self, request):
        """ Returns the availability of real time sessions for the next week.
            Takes into account nighttime and downtime and what the user has time for.

            Returns: dictionary of telescope to list of available time ranges as [start, end]
        """
        telescope = request.query_params.get('telescope', None)
        realtime_availability = get_realtime_availability(request.user, telescope)
        return Response(realtime_availability)

    def get_example_response(self):
        return {'list': Response(EXAMPLE_RESPONSES['observations']['list_real_time'], status=200)}.get(self.action)


class ScheduleViewSet(ListAsDictMixin, CreateListModelMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminOrReadOnly | IsDirectUser,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = import_string(settings.SERIALIZERS['observations']['Schedule'])
    filterset_class = ObservationFilter
    schema = ObservationPortalSchema(tags=['Observations'])
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user, submitter_id=self.request.user.id)

    def get_queryset(self):
        return observations_queryset(self.request)

    def create(self, request, *args, **kwargs):
        """ This sets the last scheduled time on a site when any directly submitted request is submitted for that site
        """
        cache_key = 'observation_portal_last_schedule_time'
        created_obs = super().create(request, args, kwargs)
        sites = get_sites_from_request(request)
        for site in sites:
            cache.set(f"{cache_key}_{site}", timezone.now(), None)
        return created_obs

    def get_example_response(self):
        return {'list': Response(EXAMPLE_RESPONSES['observations']['list_schedule'], status=200)}.get(self.action)


class ObservationViewSet(CreateListModelMixin, ListAsDictMixin, viewsets.ModelViewSet):
    permission_classes = (IsAdminOrReadOnly | IsDirectUser,)
    http_method_names = ['get', 'post', 'head', 'options', 'patch']
    filterset_class = ObservationFilter
    serializer_class = import_string(settings.SERIALIZERS['observations']['Observation'])
    schema = ObservationPortalSchema(tags=['Observations'])
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def get_queryset(self):
        return observations_queryset(self.request).prefetch_related('request__windows', 'request__location').distinct()

    @action(detail=False, methods=['get'])
    def filters(self, request):
        """ Endpoint for querying the currently available observation filters
        """
        obs_filter_options = {'fields': [], 'choice_fields': []}
        for filter_name, filter_field in self.filterset_class.get_filters().items():
            if hasattr(filter_field.field, 'choices'):
                obs_filter_options['choice_fields'].append({
                    'name': filter_name,
                    'options': list(filter_field.field.choices)
                })
            else:
                obs_filter_options['fields'].append(filter_name)

        response_serializer = self.get_response_serializer(data=obs_filter_options)
        if response_serializer.is_valid():
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
        else:
            return Response(response_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def cancel(self, request):
        """
        Filters a set of observations based on the parameters provided, and then either deletes them if they are
        scheduled >72 hours in the future, cancels them if they are in the future, or aborts them if they are currently
        in progress.
        """
        request_serializer = self.get_request_serializer(data=request.data)
        if request_serializer.is_valid():
            observations = self.get_queryset()
            # Two modes of cancelling, by id or by start/end time range
            if 'ids' in request_serializer.data:
                observations = observations.filter(pk__in=request_serializer.data['ids'])
            else:
                if 'start' in request_serializer.data:
                    observations = observations.filter(end__gt=request_serializer.data['start'])
                if 'end' in request_serializer.data:
                    observations = observations.filter(start__lt=request_serializer.data['end'])
            if 'site' in request_serializer.data:
                observations = observations.filter(site=request_serializer.data['site'])
            if 'enclosure' in request_serializer.data:
                observations = observations.filter(enclosure=request_serializer.data['enclosure'])
            if 'telescope' in request_serializer.data:
                observations = observations.filter(telescope=request_serializer.data['telescope'])
            if not request_serializer.data.get('include_normal', True):
                observations = observations.exclude(
                    request__request_group__observation_type__in=[RequestGroup.TIME_CRITICAL, RequestGroup.NORMAL])
            if not request_serializer.data.get('include_rr', False):
                observations = observations.exclude(
                    request__request_group__observation_type=RequestGroup.RAPID_RESPONSE)
            if not request_serializer.data.get('include_direct', False):
                observations = observations.exclude(request__request_group__observation_type__in=RequestGroup.NON_SCHEDULED_TYPES)
            if request.user and not request.user.is_staff:
                observations = observations.filter(request__request_group__proposal__direct_submission=True)
            # First check if we have an in_progress observation that overlaps with the time range and resource.
            # If we do and preemption is not enabled in the call, return a 400 error without cancelling anything.
            if observations.filter(state='IN_PROGRESS').count() > 0 and not request_serializer.data.get('preemption_enabled', False):
                return Response({'error': 'Cannot cancel IN_PROGRESS observations unless preemption_enabled is True'}, status=status.HTTP_400_BAD_REQUEST)
            observations = observations.filter(state__in=['PENDING', 'IN_PROGRESS'])

            num_canceled = Observation.cancel(observations)
            response_serializer = self.get_response_serializer({'canceled': num_canceled})
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
            sites = get_sites_from_request(request)
            for site in sites:
                cache.set(cache_key + f"_{site}", timezone.now(), None)
            return Response({'num_created': len(observations), 'errors': errors}, status=status.HTTP_201_CREATED)

    def get_request_serializer(self, *args, **kwargs):
        serializers = {'cancel': import_string(settings.SERIALIZERS['observations']['Cancel'])}

        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        serializers = {'cancel': import_string(settings.SERIALIZERS['observations']['CancelResponse']),
                       'filters': import_string(settings.SERIALIZERS['observations']['ObservationFilters'])}

        return serializers.get(self.action, self.serializer_class)(*args, **kwargs)

    def get_endpoint_name(self):
        endpoint_names = {'cancel': 'cancelObservation',
                          'filters': 'getObservationFilters'}

        return endpoint_names.get(self.action)


class ConfigurationStatusViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    http_method_names = ['get', 'patch']
    serializer_class = import_string(settings.SERIALIZERS['observations']['ConfigurationStatus'])
    filterset_class = ConfigurationStatusFilter
    schema = ObservationPortalSchema(tags=['Observations'])
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    queryset = ConfigurationStatus.objects.all().prefetch_related('summary')
    ordering = ('-id',)
