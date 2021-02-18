import logging

from rest_framework import viewsets, filters
from rest_framework.decorators import action, list_route
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser
from django.utils import timezone
from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from dateutil.parser import parse
from django.contrib.auth.models import User

from observation_portal.proposals.models import Proposal, Semester, TimeAllocation
from observation_portal.requestgroups.models import (RequestGroup, Request, DraftRequestGroup, InstrumentConfig,
                                                     Configuration)
from observation_portal.requestgroups.filters import RequestGroupFilter, RequestFilter
from observation_portal.requestgroups.cadence import expand_cadence_request
from observation_portal.requestgroups.serializers import RequestSerializer, RequestGroupSerializer
from observation_portal.requestgroups.serializers import DraftRequestGroupSerializer, CadenceRequestSerializer
from observation_portal.requestgroups.duration_utils import (
    get_request_duration_dict, get_max_ipp_for_requestgroup, OVERHEAD_ALLOWANCE
)
from observation_portal.common.state_changes import InvalidStateChange, TERMINAL_REQUEST_STATES
from observation_portal.requestgroups.request_utils import (
    get_airmasses_for_request_at_sites, get_telescope_states_for_request
)
from observation_portal.common.mixins import ListAsDictMixin

logger = logging.getLogger(__name__)


class RequestGroupViewSet(ListAsDictMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = RequestGroupSerializer
    filter_class = RequestGroupFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def get_throttles(self):
        actions_to_throttle = ['cancel', 'validate', 'create']
        if self.action in actions_to_throttle:
            self.throttle_scope = 'requestgroups.' + self.action
        return super().get_throttles()

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.profile.staff_view and self.request.user.is_staff:
                qs = RequestGroup.objects.all()
            else:
                qs = RequestGroup.objects.filter(proposal__in=self.request.user.proposal_set.all())
                if self.request.user.profile.view_authored_requests_only:
                    qs = qs.filter(submitter=self.request.user)
        else:
            qs = RequestGroup.objects.filter(proposal__in=Proposal.objects.filter(public=True))
        return qs.prefetch_related(
            'requests', 'requests__windows', 'requests__configurations', 'requests__location',
            'requests__configurations__instrument_configs', 'requests__configurations__target',
            'requests__configurations__acquisition_config', 'submitter', 'proposal',
            'requests__configurations__guiding_config', 'requests__configurations__constraints',
            'requests__configurations__instrument_configs__rois'
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=(IsAdminUser,))
    def schedulable_requests(self, request):
        """
            Gets the set of schedulable User requests for the scheduler, should be called right after isDirty finishes
            Needs a start and end time specified as the range of time to get requests in. Usually this is the entire
            semester for a scheduling run.
        """
        current_semester = Semester.current_semesters().first()
        start = parse(request.query_params.get('start', str(current_semester.start))).replace(tzinfo=timezone.utc)
        end = parse(request.query_params.get('end', str(current_semester.end))).replace(tzinfo=timezone.utc)
        telescope_class = request.query_params.get('telescope_class')
        # Schedulable requests are not in a terminal state, are part of an active proposal,
        # and have a window within this semester
        instrument_config_query = InstrumentConfig.objects.prefetch_related('rois')
        configuration_query = Configuration.objects.select_related(
            'constraints', 'target', 'acquisition_config', 'guiding_config').prefetch_related(
            Prefetch('instrument_configs', queryset=instrument_config_query)
        )
        request_query = Request.objects.select_related('location').prefetch_related(
            'windows', Prefetch('configurations', queryset=configuration_query)
        )
        queryset = RequestGroup.objects.exclude(
            state__in=TERMINAL_REQUEST_STATES
        ).exclude(
            observation_type=RequestGroup.DIRECT
        ).filter(
            requests__windows__start__lte=end,
            requests__windows__start__gte=start,
            proposal__active=True
        ).prefetch_related(
            Prefetch('requests', queryset=request_query),
            Prefetch('proposal', queryset=Proposal.objects.only('id').all()),
            Prefetch('submitter', queryset=User.objects.only('username', 'is_staff').all())
        ).distinct()
        if telescope_class:
            queryset = queryset.filter(requests__location__telescope_class__iexact=telescope_class)

        # queryset now contains all the schedulable URs and their associated requests and data
        # Check that each request time available in its proposal still
        request_group_data = []
        tas = {}
        for request_group in queryset.all():
            total_duration_dict = request_group.total_duration
            for tak, duration in total_duration_dict.items():
                if (tak, request_group.proposal.id) in tas:
                    time_allocation = tas[(tak, request_group.proposal.id)]
                else:
                    time_allocation = TimeAllocation.objects.get(
                        semester=tak.semester,
                        instrument_type=tak.instrument_type,
                        proposal=request_group.proposal.id,
                    )
                    tas[(tak, request_group.proposal.id)] = time_allocation
                if request_group.observation_type == RequestGroup.NORMAL:
                    time_left = time_allocation.std_allocation - time_allocation.std_time_used
                elif request_group.observation_type == RequestGroup.RAPID_RESPONSE:
                    time_left = time_allocation.rr_allocation - time_allocation.rr_time_used
                elif request_group.observation_type == RequestGroup.TIME_CRITICAL:
                    time_left = time_allocation.tc_allocation - time_allocation.tc_time_used
                else:
                    logger.critical('request_group {} observation_type {} is not allowed'.format(
                        request_group.id,
                        request_group.observation_type)
                    )
                    continue
                if time_left * OVERHEAD_ALLOWANCE >= (duration / 3600.0):
                    request_group_dict = request_group.as_dict()
                    request_group_dict['is_staff'] = request_group.submitter.is_staff
                    request_group_data.append(request_group_dict)
                    break
                else:
                    logger.warning(
                        'not enough time left {0} in proposal {1} for ur {2} of duration {3}, skipping'.format(
                            time_left, request_group.proposal.id, request_group.id, (duration / 3600.0)
                        )
                    )
        return Response(request_group_data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        request_group = self.get_object()
        try:
            request_group.state = 'CANCELED'
            request_group.save()
        except InvalidStateChange as exc:
            return Response({'errors': [str(exc)]}, status=400)
        return Response(RequestGroupSerializer(request_group).data)

    @list_route(methods=['post'])
    def validate(self, request):
        serializer = RequestGroupSerializer(data=request.data, context={'request': request})
        req_durations = {}
        if serializer.is_valid():
            req_durations = get_request_duration_dict(serializer.validated_data['requests'], request.user.is_staff)
            errors = {}
        else:
            errors = serializer.errors

        return Response({'request_durations': req_durations,
                         'errors': errors})

    @action(detail=False, methods=['post'])
    def max_allowable_ipp(self, request):
        # change requested ipp to 1 because we want it to always pass the serializers ipp check
        request.data['ipp_value'] = 1.0
        serializer = RequestGroupSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            ipp_dict = get_max_ipp_for_requestgroup(serializer.validated_data)
            return Response(ipp_dict)
        else:
            return Response({'errors': serializer.errors})

    @action(detail=False, methods=['post'])
    def cadence(self, request):
        expanded_requests = []
        for req in request.data.get('requests', []):
            if isinstance(req, dict) and req.get('cadence'):
                cadence_request_serializer = CadenceRequestSerializer(data=req)
                if cadence_request_serializer.is_valid():
                    expanded_requests.extend(expand_cadence_request(cadence_request_serializer.validated_data,
                                                                    request.user.is_staff))
                else:
                    return Response(cadence_request_serializer.errors, status=400)
            else:
                expanded_requests.append(req)

        # if we couldn't find any valid cadence requests, return that as an error
        if not expanded_requests:
            return Response({'errors': 'No visible requests within cadence window parameters'}, status=400)

        # now replace the originally sent requests with the cadence requests and send it back
        ret_data = request.data.copy()
        ret_data['requests'] = expanded_requests

        if len(ret_data['requests']) > 1:
            ret_data['operator'] = 'MANY'
        request_group_serializer = RequestGroupSerializer(data=ret_data, context={'request': request})
        if not request_group_serializer.is_valid():
            return Response(request_group_serializer.errors, status=400)
        return Response(ret_data)


class RequestViewSet(ListAsDictMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    serializer_class = RequestSerializer
    filter_class = RequestFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)
    ordering_fields = ('id', 'state')

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.profile.staff_view and self.request.user.is_staff:
                qs = Request.objects.all()
            else:
                qs = Request.objects.filter(request_group__proposal__in=self.request.user.proposal_set.all())
                if self.request.user.profile.view_authored_requests_only:
                    qs = qs.filter(request_group__submitter=self.request.user)
        else:
            qs = Request.objects.filter(request_group__proposal__in=Proposal.objects.filter(public=True))
        return qs.prefetch_related(
            'windows', 'configurations', 'location', 'configurations__instrument_configs', 'configurations__target',
            'configurations__acquisition_config', 'configurations__guiding_config', 'configurations__constraints',
            'configurations__instrument_configs__rois'
        ).distinct()

    @action(detail=True)
    def airmass(self, request, pk=None):
        return Response(get_airmasses_for_request_at_sites(self.get_object().as_dict(), is_staff=request.user.is_staff))

    @action(detail=True)
    def telescope_states(self, request, pk=None):
        telescope_states = get_telescope_states_for_request(self.get_object().as_dict(), is_staff=request.user.is_staff)
        str_telescope_states = {str(k): v for k, v in telescope_states.items()}
        return Response(str_telescope_states)

    @action(detail=True)
    def observations(self, request, pk=None):
        observations = self.get_object().observation_set.order_by('id').all()
        if request.GET.get('exclude_canceled'):
            return Response([o.as_dict(no_request=True) for o in observations if o.state != 'CANCELED'])
        return Response([o.as_dict(no_request=True) for o in observations])


class DraftRequestGroupViewSet(viewsets.ModelViewSet):
    serializer_class = DraftRequestGroupSerializer
    ordering = ('-modified',)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return DraftRequestGroup.objects.all()
        elif self.request.user.is_authenticated:
            return DraftRequestGroup.objects.filter(proposal__in=self.request.user.proposal_set.all())
        else:
            return DraftRequestGroup.objects.none()
