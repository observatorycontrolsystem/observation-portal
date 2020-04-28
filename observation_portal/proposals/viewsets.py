from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.schemas.openapi import AutoSchema

from observation_portal.common.mixins import ListAsDictMixin
from observation_portal.proposals.filters import SemesterFilter, ProposalFilter
from observation_portal.proposals.models import Proposal, Semester
from observation_portal.proposals.serializers import ProposalSerializer, SemesterSerialzer


class ProposalViewSet(ListAsDictMixin, viewsets.ReadOnlyModelViewSet):
    schema = AutoSchema(tags=['Proposals API'])
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


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    schema = AutoSchema(tags=['Proposals API'])
    permission_classes = (AllowAny,)
    serializer_class = SemesterSerialzer
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SemesterFilter
    ordering = ('-start',)
    queryset = Semester.objects.all()

