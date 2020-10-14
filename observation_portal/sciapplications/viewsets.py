from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from observation_portal.sciapplications.serializers import CallSerializer
from observation_portal.sciapplications.models import Call


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (AllowAny,)
    serializer_class = CallSerializer

    def get_queryset(self):
        return Call.open_calls().exclude(proposal_type=Call.COLLAB_PROPOSAL)
