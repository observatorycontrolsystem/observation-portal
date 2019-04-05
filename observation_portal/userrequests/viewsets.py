from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
import logging

from observation_portal.proposals.models import Proposal
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.userrequests.filters import UserRequestFilter
from observation_portal.userrequests.conversion import (validate_userrequest, convert_userrequests_to_requestgroups,
                                                        convert_requestgroups_to_userrequests,
                                                        convert_userrequest_to_requestgroup,
                                                        convert_requestgroup_to_userrequest)
from observation_portal.requestgroups.cadence import expand_cadence_request
from observation_portal.requestgroups.serializers import RequestGroupSerializer
from observation_portal.requestgroups.serializers import CadenceRequestSerializer
from observation_portal.requestgroups.duration_utils import (
    get_max_ipp_for_requestgroup
)
from observation_portal.common.state_changes import InvalidStateChange
from observation_portal.common.mixins import ListAsDictMixin

logger = logging.getLogger(__name__)


class UserRequestViewSet(ListAsDictMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    http_method_names = ['get', 'post', 'head', 'options']
    serializer_class = RequestGroupSerializer
    filter_class = UserRequestFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering = ('-id',)

    def get_throttles(self):
        actions_to_throttle = ['cancel', 'validate', 'create']
        if self.action in actions_to_throttle:
            self.throttle_scope = 'requestgroups.' + self.action  # throttle with the requestgroups
        return super().get_throttles()

    def get_queryset(self):
        if self.request.user.is_staff:
            qs = RequestGroup.objects.all()
        elif self.request.user.is_authenticated:
            qs = RequestGroup.objects.filter(
                proposal__in=self.request.user.proposal_set.all()
            )
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

    def create(self, request, *args, **kwargs):
        errors = validate_userrequest(request.data)['errors']
        if not errors:
            requestgroups_data = convert_userrequests_to_requestgroups(request.data)
            request._full_data = requestgroups_data
            return super().create(request, *args, **kwargs)
        else:
            return Response({'errors': errors}, 400)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response_data = response.data
        response_data['results'] = convert_requestgroups_to_userrequests(response.data['results'])
        return Response(response_data, 200)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        userrequests = convert_requestgroups_to_userrequests(response.data)
        return Response(userrequests, 200)

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
        body = validate_userrequest(request.data)
        return Response(body)

    @action(detail=False, methods=['post'])
    def max_allowable_ipp(self, request):
        # change requested ipp to 1 because we want it to always pass the serializers ipp check
        request.data['ipp_value'] = 1.0
        body = validate_userrequest(request.data)
        if not body['errors']:
            rg_dict = convert_userrequest_to_requestgroup(request.data)
            ipp_dict = get_max_ipp_for_requestgroup(rg_dict)
            return Response(ipp_dict)
        else:
            return Response({'errors': body['errors']})

    @action(detail=False, methods=['post'])
    def cadence(self, request):
        expanded_requests = []
        body = validate_userrequest(request.data)
        if body['errors']:
            return Response(body, status=400)
        rg_dict = convert_userrequest_to_requestgroup(request.data)
        for req in rg_dict.get('requests', []):
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

        rg_dict['requests'] = expanded_requests
        if len(rg_dict['requests']) > 1:
            rg_dict['operator'] = 'MANY'

        # Now convert back to a userrequest and check its validity again
        ur_dict = convert_requestgroup_to_userrequest(rg_dict)
        body = validate_userrequest(ur_dict)
        if body['errors']:
            return Response(body, status=400)
        return Response(ur_dict)
