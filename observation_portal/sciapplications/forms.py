from django import forms
from django.forms import ModelForm
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext as _
from django.conf import settings
from PyPDF2 import PdfFileReader
import os

from observation_portal.sciapplications.models import ScienceApplication, Call, TimeRequest, CoInvestigator
from observation_portal.sciapplications.templatetags.sciapp_extras import file_to_s3_url
from observation_portal.proposals.models import Semester


class FakeFieldFile(object):
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __str__(self):
        return self.name


class PdfFileInput(forms.ClearableFileInput):
    def format_value(self, value):
        formatted_value = super().format_value(value)
        if formatted_value and getattr(formatted_value, 'url'):
            if settings.AWS_ACCESS_KEY_ID:
                url = file_to_s3_url(formatted_value)
                new_formatted_value = FakeFieldFile(str(formatted_value), url)
                return new_formatted_value
        return formatted_value


def validate_pdf_file(value):
    extension = os.path.splitext(value.name)[1]
    if extension not in ['.pdf', '.PDF']:
        raise forms.ValidationError(_('We can only accept PDF files.'))


class BaseProposalAppForm(ModelForm):
    call = forms.ModelChoiceField(
        queryset=Call.objects.all(),
        widget=forms.HiddenInput
    )
    status = forms.CharField(widget=forms.HiddenInput, initial='DRAFT')
    pdf = forms.FileField(widget=PdfFileInput, validators=[validate_pdf_file], required=False, label='pdf')

    def clean(self):
        super().clean()
        for field in self.Meta.required_fields:
            if not self.cleaned_data.get(field) and self.cleaned_data.get('status') == 'SUBMITTED':
                self.add_error(field, _('{}: This field is required'.format(self.fields[field].label)))
        if self.errors:
            self.add_error(None, _('There was an error with your submission.'))

    def clean_pdf(self):
        pdf = self.cleaned_data.get('pdf')
        if pdf:
            pdf_file = PdfFileReader(pdf.file)
            if pdf_file.getNumPages() > self.max_pages:
                raise forms.ValidationError(_('PDF file cannot exceed {} pages'.format(self.max_pages)))
        return pdf

    def clean_abstract(self):
        ABSTRACT_WORD_LIMIT = 500
        abstract = self.cleaned_data.get('abstract', '')
        if len(abstract.split(' ')) > ABSTRACT_WORD_LIMIT:
            raise forms.ValidationError(_('Abstract is limited to 500 words.'))
        return abstract

    def save(self, commit=True):
        # The pdf save path requires the sciapp instance id, so you must save the sciapp before saving the pdf
        saved_pdf = self.instance.pdf
        self.instance.pdf = None
        instance = super().save(commit)
        instance.pdf = saved_pdf
        instance.save()
        return instance


class ScienceProposalAppForm(BaseProposalAppForm):
    max_pages = 999

    class Meta:
        model = ScienceApplication
        fields = (
            'call', 'status', 'title', 'pi', 'pi_first_name', 'pi_last_name', 'pi_institution',
            'abstract', 'pdf'
        )
        required_fields = set(fields)


class DDTProposalAppForm(BaseProposalAppForm):
    max_pages = 999

    class Meta:
        model = ScienceApplication
        fields = (
            'call', 'status', 'title', 'pi', 'pi_first_name', 'pi_last_name', 'pi_institution',
            'pdf',
        )
        required_fields = set(fields)


class KeyProjectAppForm(BaseProposalAppForm):
    max_pages = 999

    class Meta:
        model = ScienceApplication
        fields = (
            'call', 'status', 'title', 'pi', 'pi_first_name', 'pi_last_name', 'pi_institution',
            'abstract', 'pdf'
        )
        required_fields = set(fields)


class SciCollabAppForm(BaseProposalAppForm):
    max_pages = 999

    class Meta:
        model = ScienceApplication
        fields = (
            'call', 'status', 'title', 'pi', 'pi_first_name', 'pi_last_name', 'pi_institution',
            'abstract', 'tac_rank'
        )
        required_fields = set(fields)

    def __init__(self, *args, **kwargs):
        # Need this because base proposal app form has pdf hardcoded as a field
        super().__init__(*args, **kwargs)
        self.fields.pop('pdf')


class TimeRequestForm(ModelForm):
    semester = forms.ModelChoiceField(queryset=Semester.future_semesters(), required=False)

    class Meta:
        model = TimeRequest
        exclude = ('approved',)

    def clean_semester(self):
        semester = self.cleaned_data.get('semester')
        if not semester:
            return Semester.future_semesters().first()
        return semester

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.science_application.call.proposal_type != 'KEY':
            instance.semester = instance.science_application.call.semester
        if commit:
            instance.save()
        return instance


timerequest_formset = inlineformset_factory(
    ScienceApplication, TimeRequest, form=TimeRequestForm, extra=1
)


class CIForm(ModelForm):
    class Meta:
        model = CoInvestigator
        fields = '__all__'


ci_formset = inlineformset_factory(
    ScienceApplication, CoInvestigator, form=CIForm, extra=1
)
