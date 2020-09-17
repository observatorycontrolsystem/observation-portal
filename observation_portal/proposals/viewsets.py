from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.translation import ugettext as _

from observation_portal.common.mixins import ListAsDictMixin
from observation_portal.proposals.filters import SemesterFilter, ProposalFilter
from observation_portal.proposals.models import Proposal, Semester, ProposalNotification, Membership
from observation_portal.proposals.serializers import (
    ProposalSerializer, SemesterSerialzer, ProposalNotificationSerializer, TimeLimitSerializer,
    ProposalInviteSerializer, ProposalInviteDeleteSerializer, MembershipDeleteSerializer
)
from observation_portal.accounts.permissions import IsPrincipleInvestigator


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

    @action(detail=True, methods=['post'])
    def proposalnotifications(self, request, pk=None):
        proposal = self.get_object()
        serializer = ProposalNotificationSerializer(data=request.data)
        if serializer.is_valid():
            if serializer.validated_data['enabled']:
                ProposalNotification.objects.get_or_create(user=request.user, proposal=proposal)
            else:
                ProposalNotification.objects.filter(user=request.user, proposal=proposal).delete()
            return Response({'message': 'Preferences saved'})
        else:
            return Response({'errors': serializer.errors}, 400)

    @action(detail=True, methods=['post'], permission_classes=(IsPrincipleInvestigator,))
    def limit(self, request, pk=None):
        proposal = self.get_object()
        serializer = TimeLimitSerializer(data=request.data)
        if serializer.is_valid():
            time_limit_hours = serializer.validated_data['time_limit_hours']
            usernames = serializer.validated_data['usernames']
            memberships_to_update = proposal.membership_set.filter(
                role=Membership.CI, user__username__in=usernames
            )
            n_updated = memberships_to_update.update(time_limit=time_limit_hours * 3600)
            return Response({'message': f'Updated {n_updated} CI time limits to {time_limit_hours} hours'})
        else:
            return Response({'errors': serializer.errors}, 400)

    @action(detail=True, methods=['get'], permission_classes=(IsPrincipleInvestigator,))
    def invitations(self, request, pk=None):
        proposal = self.get_object()
        serializer = ProposalInviteSerializer(proposal.proposalinvite_set.all(), many=True)
        return Response(serializer.data)

    @invitations.mapping.delete
    def delete_invitation(self, request, pk=None):
        proposal = self.get_object()
        serializer = ProposalInviteDeleteSerializer(data=request.data)
        if serializer.is_valid():
            invitation_id = serializer.validated_data['invitation_id']
            deleted = proposal.proposalinvite_set.filter(pk=invitation_id, used=None).delete()
            return Response({'message': f'Deleted {deleted[0]} invitation(s)'})
        else:
            return Response({'errors': serializer.errors}, status=400)

    @invitations.mapping.post
    def send_invitation(self, request, pk=None):
        proposal = self.get_object()
        serializer = ProposalInviteSerializer(
            data=request.data,
            context={'user': self.request.user, 'proposal': proposal}
        )
        if serializer.is_valid():
            proposal.add_users(serializer.validated_data['emails'], Membership.CI)
            return Response({'message': _('Co Investigator(s) invited')})
        else:
            return Response(serializer.errors, status=400)

    @action(detail=True, methods=['delete'], permission_classes=(IsPrincipleInvestigator,))
    def memberships(self, request, pk=None):
        proposal = self.get_object()
        serializer = MembershipDeleteSerializer(data=request.data)
        if serializer.is_valid():
            membership_id = serializer.validated_data['membership_id']
            deleted = proposal.membership_set.filter(pk=membership_id, role=Membership.CI).delete()
            return Response({'message': f'Deleted {deleted[0]} membership(s)'})
        else:
            return Response({'errors': serializer.errors}, status=400)


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SemesterSerialzer
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SemesterFilter
    ordering = ('-start',)
    queryset = Semester.objects.all()
