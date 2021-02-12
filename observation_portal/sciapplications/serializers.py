import os

from django.utils.translation import ugettext as _
from django.utils import timezone
from django.db import transaction
from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError
from rest_framework import serializers

from observation_portal.sciapplications.models import ScienceApplication, Call, TimeRequest, CoInvestigator


class CallSerializer(serializers.ModelSerializer):
    proposal_type_display = serializers.SerializerMethodField()
    instruments = serializers.SerializerMethodField()
    time_requested = serializers.SerializerMethodField()

    class Meta:
        model = Call
        fields = (
            'id', 'semester', 'eligible_semesters', 'proposal_type', 'proposal_type_display',
            'eligibility_short', 'eligibility', 'deadline', 'instruments', 'time_requested'
        )

    def get_proposal_type_display(self, obj):
        return obj.get_proposal_type_display()

    def get_instruments(self, obj):
        return [instrument.as_dict() for instrument in obj.instruments.all()]

    def get_time_requested(self, obj):
        time_requested = None
        if obj.proposal_type == Call.COLLAB_PROPOSAL:
            sca = self.context['request'].user.sciencecollaborationallocation
            time_requested = sca.time_requested_for_semester(obj.semester, Call.COLLAB_PROPOSAL)
        return time_requested


class CoInvestigatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoInvestigator
        fields = ('first_name', 'last_name', 'institution', 'email')


class TimeRequestSerializer(serializers.ModelSerializer):
    telescope_name = serializers.SerializerMethodField()
    instrument_name = serializers.SerializerMethodField()
    instrument_code = serializers.SerializerMethodField()

    class Meta:
        model = TimeRequest
        fields = (
            'semester', 'std_time', 'rr_time', 'tc_time', 'instrument', 'telescope_name',
            'instrument_name', 'instrument_code'
        )

    def get_telescope_name(self, obj):
        return obj.instrument.telescope_name

    def get_instrument_name(self, obj):
        return obj.instrument.display

    def get_instrument_code(self, obj):
        return obj.instrument.code


class CallsPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        if self.context['request'].user.profile.is_scicollab_admin:
            return Call.objects.all()
        else:
            return Call.objects.exclude(proposal_type=Call.COLLAB_PROPOSAL)


class ScienceApplicationSerializer(serializers.ModelSerializer):
    title = serializers.CharField(required=True)
    status = serializers.CharField(required=True)
    call_id = CallsPrimaryKeyRelatedField(required=True, source='call', write_only=True)
    coinvestigator_set = CoInvestigatorSerializer(many=True, required=False)
    timerequest_set = TimeRequestSerializer(many=True, required=False)
    pdf = serializers.FileField(required=False)
    clear_pdf = serializers.BooleanField(required=False, default=False, write_only=True)
    call = serializers.SerializerMethodField()
    sca = serializers.SerializerMethodField()
    submitter = serializers.SerializerMethodField()

    class Meta:
        model = ScienceApplication
        fields = (
            'id', 'title', 'abstract', 'status', 'tac_rank', 'call', 'call_id', 'pi',
            'pi_first_name', 'pi_last_name', 'pi_institution', 'timerequest_set',
            'coinvestigator_set', 'pdf', 'clear_pdf', 'sca', 'submitter', 'submitted'
        )
        read_only_fields = ('submitted', )

    def get_sca(self, obj):
        return {
            'id': obj.sca.id,
            'name': obj.sca.name
        }

    def get_submitter(self, obj):
        return {
            'first_name': obj.submitter.first_name,
            'last_name': obj.submitter.last_name,
            'institution': obj.submitter.profile.institution
        }

    def get_call(self, obj):
        return {
            'id': obj.call.id,
            'semester': obj.call.semester.id,
            'proposal_type': obj.call.proposal_type,
            'proposal_type_display': obj.call.get_proposal_type_display(),
            'deadline': obj.call.deadline,
            'eligibility': obj.call.eligibility
        }

    def validate_status(self, status):
        # Other application statuses are set via admin actions, these are the only valid ones
        # that can be set here.
        valid_statuses = (ScienceApplication.DRAFT, ScienceApplication.SUBMITTED)
        if status not in valid_statuses:
            raise serializers.ValidationError(_(f'Application status must be one of [{", ".join(valid_statuses)}]'))
        return status

    def validate_call_id(self, call):
        if not call.opens <= timezone.now() <= call.deadline:
            raise serializers.ValidationError(_('The call is not open.'))
        return call

    def validate_pdf(self, pdf):
        extension = os.path.splitext(pdf.name)[1]
        if extension not in ['.pdf', '.PDF']:
            raise serializers.ValidationError(_('We can only accept PDF files.'))

        try:
            PdfFileReader(pdf.file)
        except PdfReadError:
            raise serializers.ValidationError(_('Invalid PDF file.'))

        return pdf

    def validate_abstract(self, abstract):
        abstract_word_limit = 500
        if len(abstract.split(' ')) > abstract_word_limit:
            raise serializers.ValidationError(_('Abstract is limited to 500 words.'))
        return abstract

    @staticmethod
    def get_required_fields_for_submission(call_proposal_type):
        required_fields = ['call', 'status', 'title', 'pi', 'pi_first_name', 'pi_last_name', 'pi_institution']
        if call_proposal_type == Call.DDT_PROPOSAL:
            required_fields.extend(['pdf'])
        elif call_proposal_type == Call.COLLAB_PROPOSAL:
            required_fields.extend(['abstract', 'tac_rank'])
        else:
            required_fields.extend(['abstract', 'pdf'])
        return required_fields

    def validate(self, data):
        status = data['status']
        call = data['call']
        clear_pdf = data.get('clear_pdf', False)
        pdf = data.get('pdf', None)
        timerequest_set = data.get('timerequest_set', [])
        tac_rank = data.get('tac_rank', 0)

        if pdf is not None and clear_pdf:
            raise serializers.ValidationError(_('Please either submit a new pdf or clear the existing pdf, not both.'))

        if pdf is not None and call.proposal_type == Call.COLLAB_PROPOSAL:
            raise serializers.ValidationError(_('Science collaboration proposals do not have pdfs.'))

        for timerequest in timerequest_set:
            if timerequest['semester'].id not in call.eligible_semesters:
                raise serializers.ValidationError(_(
                    f'The semesters set for the time requests of this application must be one '
                    f'of [{", ".join(call.eligible_semesters)}]'
                ))
            call_instrument_ids = [instrument.id for instrument in call.instruments.all()]
            if timerequest['instrument'].id not in call_instrument_ids:
                raise serializers.ValidationError(_(
                    f'The instrument IDs set for the time requests of this application must be one '
                    f'of [{", ".join([str(i) for i in call_instrument_ids])}]'
                ))

        unique_time_requests = set([f'{tr["instrument"]}-{tr["semester"]}' for tr in timerequest_set])
        if len(unique_time_requests) != len(timerequest_set):
            raise serializers.ValidationError(_(
                'You cannot create more than one time request for the same semester and instrument. Please '
                'consolidate your time requests.'
            ))

        if tac_rank > 0 and call.proposal_type != Call.COLLAB_PROPOSAL:
            raise serializers.ValidationError(_(
                f'{call.get_proposal_type_display()} applications are not allowed to set tac_rank'
            ))

        if status == ScienceApplication.SUBMITTED:
            if len(timerequest_set) < 1:
                raise serializers.ValidationError(_(
                    'You must provide at least one time request to submit an application'
                ))

            missing_fields = {}
            for field in self.get_required_fields_for_submission(call.proposal_type):
                empty_values = [None, '']
                field_is_empty = data.get(field) in empty_values
                if field == 'pdf':
                    if clear_pdf:
                        missing_fields['clear_pdf'] = _(
                            'A PDF is required for submission. If you want to clear the uploaded PDF, please '
                            'either upload a different PDF or save the application as a draft.'
                        )
                    elif field_is_empty and not getattr(self.instance, 'pdf', None):
                        missing_fields[field] = _('A PDF is required for submission.')
                else:
                    if field_is_empty:
                        missing_fields[field] = _('This field is required.')

            if missing_fields:
                raise serializers.ValidationError(missing_fields)

            data['submitted'] = timezone.now()

        return data

    def update(self, instance, validated_data):
        # TODO: Do this without needing to delete all existing time requests and coinvestigators
        pdf = validated_data.pop('pdf', None)
        clear_pdf = validated_data.pop('clear_pdf', False)
        timerequest_set = validated_data.pop('timerequest_set', [])
        coinvestigator_set = validated_data.pop('coinvestigator_set', [])

        with transaction.atomic():
            for field, value in validated_data.items():
                setattr(instance, field, value)

            # The pdf may be set to `None` because a user does not want to change their previously
            # uploaded pdf. Use `clear_pdf` to determine if the pdf should be cleared.
            if pdf is not None:
                instance.pdf = pdf
            elif clear_pdf:
                instance.pdf = None

            instance.save()

            for timerequest in instance.timerequest_set.all():
                timerequest.delete()
            for coinvestigator in instance.coinvestigator_set.all():
                coinvestigator.delete()

            for timerequest in timerequest_set:
                TimeRequest.objects.create(**timerequest, science_application=instance)
            for coinvestigator in coinvestigator_set:
                CoInvestigator.objects.create(**coinvestigator, science_application=instance)

        return instance

    def create(self, validated_data):
        validated_data.pop('clear_pdf', False)
        timerequest_set = validated_data.pop('timerequest_set', [])
        coinvestigator_set = validated_data.pop('coinvestigator_set', [])

        with transaction.atomic():
            sciapp = ScienceApplication.objects.create(**validated_data, submitter=self.context['request'].user)
            for timerequest in timerequest_set:
                TimeRequest.objects.create(**timerequest, science_application=sciapp)
            for coinvestigator in coinvestigator_set:
                CoInvestigator.objects.create(**coinvestigator, science_application=sciapp)

        return sciapp
