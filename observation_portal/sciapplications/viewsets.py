from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.module_loading import import_string

from observation_portal.accounts.tasks import send_mail
from observation_portal.sciapplications.filters import ScienceApplicationFilter, CallFilter
from observation_portal.sciapplications.models import ScienceApplication, Call


class CallViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated,)
    filter_class = CallFilter
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
    filter_class = ScienceApplicationFilter
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
