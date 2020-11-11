from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from django.template.loader import render_to_string

from observation_portal.accounts.tasks import send_mail
from observation_portal.sciapplications.serializers import (
    ScienceApplicationCreateSerializer, ScienceApplicationReadSerializer, CallSerializer,
    get_calls_queryset
)
from observation_portal.sciapplications.filters import ScienceApplicationFilter
from observation_portal.sciapplications.models import ScienceApplication, Call


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = CallSerializer

    def get_queryset(self):
        return get_calls_queryset(self.request)


class ScienceApplicationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, )
    filter_class = ScienceApplicationFilter
    http_method_names = ('get', 'head', 'options', 'post', 'put', 'delete')
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering_fields = (
        ('call__semester', 'semester'),
        ('tac_rank', 'tac_rank')
    )

    def get_queryset(self):
        if self.request.user.is_staff and self.request.user.profile.staff_view:
            qs = ScienceApplication.objects.all()
        else:
            qs = ScienceApplication.objects.filter(submitter=self.request.user)

        # Only DRAFT applications are allowed to be updated
        if self.action == 'update':
            qs = qs.filter(status=ScienceApplication.DRAFT)

        return qs.prefetch_related(
            'call', 'call__semester', 'submitter', 'submitter__profile', 'submitter__sciencecollaborationallocation',
            'timerequest_set', 'timerequest_set__instrument', 'coinvestigator_set',
        )

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ScienceApplicationReadSerializer
        else:
            return ScienceApplicationCreateSerializer

    @action(detail=True, methods=['get'])
    def pdf(self):
        return Response({'message': 'This will return a pdf'})

    def perform_destroy(self, instance):
        if instance.status == ScienceApplication.DRAFT:
            instance.delete()

    def perform_update(self, serializer):
        instance = serializer.save()
        send_email_if_ddt_submission(instance)

    def perform_create(self, serializer):
        instance = serializer.save()
        send_email_if_ddt_submission(instance)


def send_email_if_ddt_submission(science_application):
    is_submitted = science_application.status == ScienceApplication.SUBMITTED
    is_ddt = science_application.call.proposal_type == Call.DDT_PROPOSAL
    if is_submitted and is_ddt:
        message = render_to_string('sciapplications/ddt_submitted.txt', {'ddt': science_application})
        send_mail.send(
            'LCO Director\'s Discretionary Time Submission',
            message,
            'portal@lco.global',
            [science_application.submitter.email, 'ddt@lco.global']
        )
