from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from dateutil.parser import parse
import logging

from observation_portal.proposals.models import Proposal, Semester, TimeAllocation
from observation_portal.requestgroups.models import RequestGroup, Request, DraftRequestGroup
from observation_portal.requestgroups.filters import RequestGroupFilter, RequestFilter
from observation_portal.requestgroups.cadence import expand_cadence_request
from observation_portal.requestgroups.serializers import RequestSerializer, RequestGroupSerializer
from observation_portal.requestgroups.serializers import DraftRequestGroupSerializer, CadenceRequestSerializer
from observation_portal.requestgroups.duration_utils import (get_request_duration_dict, get_max_ipp_for_requestgroup,
                                                  OVERHEAD_ALLOWANCE)
from observation_portal.requestgroups.state_changes import InvalidStateChange, TERMINAL_STATES
from observation_portal.requestgroups.request_utils import (get_airmasses_for_request_at_sites,
                                                 get_telescope_states_for_request)
logger = logging.getLogger(__name__)


class RequestGroupViewSet(viewsets.ModelViewSet):
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
        return RequestGroup.objects.all()
        # if self.request.user.is_staff:
        #     qs = RequestGroup.objects.all()
        # elif self.request.user.is_authenticated:
        #     qs = RequestGroup.objects.filter(
        #         proposal__in=self.request.user.proposal_set.all()
        #     )
        # else:
        #     qs = RequestGroup.objects.filter(proposal__in=Proposal.objects.filter(public=True))
        # return qs.prefetch_related('requests', 'requests__windows', 'requests__configurations', 'requests__location')

    def perform_create(self, serializer):
        serializer.save(submitter=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=(IsAdminUser,))
    def schedulable_requests(self, request):
        '''
            Gets the set of schedulable User requests for the scheduler, should be called right after isDirty finishes
            Needs a start and end time specified as the range of time to get requests in. Usually this is the entire
            semester for a scheduling run.
        '''
        current_semester = Semester.current_semesters().first()
        start = parse(request.query_params.get('start', str(current_semester.start))).replace(tzinfo=timezone.utc)
        end = parse(request.query_params.get('end', str(current_semester.end))).replace(tzinfo=timezone.utc)

        # Schedulable requests are not in a terminal state, are part of an active proposal,
        # and have a window within this semester
        queryset = RequestGroup.objects.exclude(state__in=TERMINAL_STATES).filter(
            requests__windows__start__lte=end,
            requests__windows__start__gte=start,
            proposal__active=True
        ).prefetch_related(
            'requests', 'requests__windows', 'proposal', 'proposal__timeallocation_set', 'requests__configurations',
            'submitter', 'requests__location'
        ).distinct()

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
                        instrument_name=tak.instrument_name,
                        telescope_class=tak.telescope_class,
                        proposal=request_group.proposal.id,
                    )
                    tas[(tak, request_group.proposal.id)] = time_allocation
                if request_group.observation_type == RequestGroup.NORMAL:
                    time_left = time_allocation.std_allocation - time_allocation.std_time_used
                elif request_group.observation_type == RequestGroup.RAPID_RESPONSE:
                    time_left = time_allocation.rr_allocation - time_allocation.rr_time_used
                else:
                    time_left = time_allocation.tc_allocation - time_allocation.tc_time_used
                if time_left * OVERHEAD_ALLOWANCE >= (duration / 3600.0):
                    request_group_data.append(request_group.as_dict)
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

    @action(detail=False, methods=['post'])
    def validate(self, request):
        serializer = RequestGroupSerializer(data=request.data, context={'request': request})
        req_durations = {}
        if serializer.is_valid():
            req_durations = get_request_duration_dict(serializer.validated_data['requests'])
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
                    expanded_requests.extend(expand_cadence_request(cadence_request_serializer.validated_data))
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


class RequestViewSet(viewsets.ReadOnlyModelViewSet):
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
        return Request.objects.all()
        # if self.request.user.is_staff:
        #     return Request.objects.all()
        # elif self.request.user.is_authenticated:
        #     return Request.objects.filter(
        #         request_group__proposal__in=self.request.user.proposal_set.all()
        #     )
        # else:
        #     return Request.objects.filter(request_group__proposal__in=Proposal.objects.filter(public=True))

    @action(detail=True)
    def airmass(self, request, pk=None):
        return Response(get_airmasses_for_request_at_sites(self.get_object().as_dict))

    @action(detail=True)
    def telescope_states(self, request, pk=None):
        telescope_states = get_telescope_states_for_request(self.get_object())
        str_telescope_states = {str(k): v for k, v in telescope_states.items()}

        return Response(str_telescope_states)

    @action(detail=True)
    def blocks(self, request, pk=None):
        blocks = self.get_object().blocks
        if request.GET.get('canceled'):
            return Response([b for b in blocks if not b['canceled']])
        return Response(blocks)


class DraftRequestGroupViewSet(viewsets.ModelViewSet):
    serializer_class = DraftRequestGroupSerializer
    ordering = ('-modified',)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return DraftRequestGroup.objects.filter(proposal__in=self.request.user.proposal_set.all())
        else:
            return DraftRequestGroup.objects.none()
