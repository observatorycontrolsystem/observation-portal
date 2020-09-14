from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404

from observation_portal.common.mixins import ListAsDictMixin
from observation_portal.proposals.filters import SemesterFilter, ProposalFilter
from observation_portal.proposals.models import Proposal, Semester, ProposalNotification, Membership
from observation_portal.proposals.serializers import (
    ProposalSerializer, SemesterSerialzer, ProposalNotificationSerializer, TimeLimitSerializer
)


class ProposalViewSet(ListAsDictMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProposalSerializer
    filter_class = ProposalFilter
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    ordering = ('-id',)

    def get_queryset(self):
        if self.request.user.is_staff:
            return Proposal.objects.all().prefetch_related(
                'users', 'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )
        else:
            return self.request.user.proposal_set.all().prefetch_related(
                'users', 'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )

    @action(detail=True, methods=['post'], permission_classes=(IsAuthenticated,))
    def proposalnotifications(self, request, pk=None):
        serializer = ProposalNotificationSerializer(data=request.data)
        if serializer.is_valid():
            if serializer.validated_data['enabled']:
                ProposalNotification.objects.get_or_create(user=request.user, proposal=self.get_object())
            else:
                ProposalNotification.objects.filter(user=request.user, proposal=self.get_object()).delete()
            return Response({'message': 'Preferences saved'})
        else:
            return Response({'errors': serializer.errors}, 400)

    @action(detail=True, methods=['post'], permission_classes=(IsAuthenticated,))
    def limit(self, request, pk=None):
        if not request.user.membership_set.filter(proposal=self.get_object(), role=Membership.PI).exists():
            raise Http404

        serializer = TimeLimitSerializer(data=request.data)
        if serializer.is_valid():
            time_limit_hours = serializer.validated_data['time_limit_hours']
            usernames = serializer.validated_data['usernames']
            memberships_to_update = self.get_object().membership_set.filter(
                role=Membership.CI, user__username__in=usernames
            )
            n_updated = memberships_to_update.update(time_limit=time_limit_hours * 3600)
            return Response({'message': f'Updated {n_updated} CI time limits to {time_limit_hours} hours'})
        else:
            return Response({'errors': serializer.errors}, 400)


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SemesterSerialzer
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SemesterFilter
    ordering = ('-start',)
    queryset = Semester.objects.all()

