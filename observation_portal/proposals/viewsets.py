from rest_framework import viewsets, filters, mixins
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.translation import ugettext as _

from observation_portal.accounts.permissions import IsPrincipleInvestigator
from observation_portal.common.mixins import ListAsDictMixin, DetailAsDictMixin
from observation_portal.proposals.filters import SemesterFilter, ProposalFilter, MembershipFilter, ProposalInviteFilter
from observation_portal.proposals.models import Proposal, Semester, ProposalNotification, Membership, ProposalInvite
from observation_portal.proposals.serializers import (
    ProposalSerializer, SemesterSerialzer, ProposalNotificationSerializer, TimeLimitSerializer,
    ProposalInviteSerializer, MembershipSerializer
)


class ProposalViewSet(ListAsDictMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProposalSerializer
    filter_class = ProposalFilter
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    ordering = ('-id',)

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return Proposal.objects.all().prefetch_related(
                'users', 'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )
        else:
            return self.request.user.proposal_set.all().prefetch_related(
                'users', 'sca', 'membership_set', 'membership_set__user', 'timeallocation_set'
            )

    @action(detail=True, methods=['post'])
    def notification(self, request, pk=None):
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
    def invite(self, request, pk=None):
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


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SemesterSerialzer
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SemesterFilter
    ordering = ('-start',)
    queryset = Semester.objects.all()

    @action(detail=True, methods=['get'])
    def proposals(self):
        # proposals = self.get_queryset().
        # If staff, add more info into response. If not staff, return a basic list of things

        # For the public page:
        # context['proposals'] = self.get_object().proposals.filter(active=True, non_science=False) \
        #     .distinct().order_by('sca__name')

        pass


class MembershipViewSet(ListAsDictMixin, DetailAsDictMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ('get', 'head', 'options', 'post', 'delete')
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = MembershipFilter
    serializer_class = MembershipSerializer

    def get_queryset(self):
        proposals = self.request.user.proposal_set.filter(membership__role=Membership.PI)
        return Membership.objects.filter(proposal__in=proposals)

    @action(detail=False, methods=['post'])
    def limit(self, request, pk=None):
        serializer = TimeLimitSerializer(data=request.data, context={'user': self.request.user})
        if serializer.is_valid():
            time_limit_hours = serializer.validated_data['time_limit_hours']
            membership_ids = serializer.validated_data['membership_ids']
            memberships_to_update = self.get_queryset().filter(role=Membership.CI, pk__in=membership_ids)
            n_updated = memberships_to_update.update(time_limit=time_limit_hours * 3600)
            return Response({'message': f'Updated {n_updated} CI time limits to {time_limit_hours} hours'})
        else:
            return Response({'errors': serializer.errors}, 400)

    def perform_destroy(self, instance):
        if instance.role == Membership.CI:
            instance.delete()


class ProposalInviteViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    http_method_names = ('get', 'head', 'options', 'delete')
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = ProposalInviteFilter
    serializer_class = ProposalInviteSerializer

    def get_queryset(self):
        proposals = self.request.user.proposal_set.filter(membership__role=Membership.PI)
        return ProposalInvite.objects.filter(proposal__in=proposals)

    def perform_destroy(self, instance):
        if instance.used is None:
            instance.delete()
