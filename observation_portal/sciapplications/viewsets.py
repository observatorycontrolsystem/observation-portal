import os

from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.module_loading import import_string
from django.core.files.base import ContentFile

from observation_portal.accounts.tasks import send_mail
from observation_portal.sciapplications.filters import ScienceApplicationFilter, CallFilter
from observation_portal.sciapplications.models import CoInvestigator, ScienceApplication, Call, TimeRequest
from observation_portal.common.schema import ObservationPortalSchema


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    schema = ObservationPortalSchema(tags=['Science Applications'])
    filterset_class = CallFilter
    serializer_class = import_string(settings.SERIALIZERS['sciapplications']['Call'])
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )

    def get_queryset(self):
        if self.request.user.profile.is_scicollab_admin:
            return Call.objects.all()
        else:
            return Call.objects.all().exclude(proposal_type=Call.COLLAB_PROPOSAL)


class ScienceApplicationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, )
    schema = ObservationPortalSchema(tags=['Science Applications'])
    filterset_class = ScienceApplicationFilter
    serializer_class = import_string(settings.SERIALIZERS['sciapplications']['ScienceApplication'])
    http_method_names = ('get', 'head', 'options', 'post', 'put', 'delete')
    filter_backends = (
        filters.OrderingFilter,
        DjangoFilterBackend
    )
    ordering_fields = (
        ('call__semester', 'semester'),
        ('tac_rank', 'tac_rank')
    )

    @action(detail=True, methods=['post'])
    def copy(self, request, pk=None):
        """
        Copy a science application's information for a new call
        """
        sci_app = self.get_object()

        # first check that there's an open call during this time, with the correct proposal type
        active_calls = Call.open_calls().filter(proposal_type=sci_app.call.proposal_type)
        if not active_calls:
            return Response({'errors': [f'No open call at this time for proposal type {sci_app.call.proposal_type}']},
                            status=status.HTTP_400_BAD_REQUEST)
        else:
            cois = sci_app.coinvestigator_set.all()
            time_requests = sci_app.timerequest_set.all()
            # make sure we auto-generate a primary key: https://docs.djangoproject.com/en/3.2/topics/db/queries/#copying-model-instances
            sci_app.pk = None
            sci_app._state.adding = True
            sci_app.status = 'DRAFT'
            sci_app.call = active_calls[0]
            sci_app.proposal = None
            sci_app.tac_rank = 0
            sci_app.tac_priority = 0
            # save the model to generate a new primary key
            sci_app.save()
            # Now add copies of the COIs and Time Requests in the new Semester
            for coi in cois:
                CoInvestigator.objects.create(
                    science_application=sci_app,
                    email=coi.email,
                    first_name=coi.first_name,
                    last_name=coi.last_name,
                    institution=coi.institution
                )
            for time_request in time_requests:
                instrument_types = time_request.instrument_types.all().intersection(active_calls[0].instruments.all())
                if instrument_types:
                    tr = TimeRequest.objects.create(
                        science_application=sci_app,
                        semester=active_calls[0].semester,
                        std_time=time_request.std_time,
                        rr_time=time_request.rr_time,
                        tc_time=time_request.tc_time
                    )
                    for instrument in instrument_types:
                        tr.instrument_types.add(instrument)
                    tr.save()
            # now generate new PDF, this uses the primary key of the new sciapp
            if sci_app.pdf:
                sci_app.pdf = ContentFile(sci_app.pdf.read(),
                                        name=os.path.basename(sci_app.pdf.name))
                sci_app.save()
            return Response(status=status.HTTP_200_OK)

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
            'timerequest_set', 'timerequest_set__instrument_types', 'coinvestigator_set',
        )

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
        message = render_to_string('sciapplications/ddt_submitted.txt', {
            'ddt': science_application,
            'detail_url': settings.SCIENCE_APPLICATION_DETAIL_URL.format(sciapp_id=science_application.id),
            'organization_name': settings.ORGANIZATION_NAME
        })
        send_mail.send(
            f'{settings.ORGANIZATION_NAME} Director\'s Discretionary Time Submission',
            message,
            settings.ORGANIZATION_EMAIL,
            [science_application.submitter.email, settings.ORGANIZATION_DDT_EMAIL]
        )
