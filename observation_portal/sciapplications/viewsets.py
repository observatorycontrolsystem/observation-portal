from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from observation_portal.sciapplications.serializers import ScienceApplicationSerializer, CallSerializer
from observation_portal.sciapplications.filters import ScienceApplicationFilter
from observation_portal.sciapplications.models import ScienceApplication, Call
from observation_portal.proposals.models import ScienceCollaborationAllocation


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = CallSerializer

    def get_queryset(self):
        if ScienceCollaborationAllocation.objects.filter(admin=self.request.user).exists():
            return Call.open_calls()
        else:
            return Call.open_calls().exclude(proposal_type=Call.COLLAB_PROPOSAL)


class ScienceApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ScienceApplicationSerializer
    permission_classes = (IsAuthenticated, )
    filter_class = ScienceApplicationFilter
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering_fields = (
        ('call__semester', 'semester'),
        'tac_rank'
    )

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            return ScienceApplication.objects.all()
        else:
            return ScienceApplication.objects.filter(submitter=self.request.user)

    def perform_destroy(self, instance):
        if instance.status == ScienceApplication.DRAFT:
            instance.delete()
