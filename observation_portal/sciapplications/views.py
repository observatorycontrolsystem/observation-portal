from django.utils.translation import ugettext as _
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.template.loader import render_to_string
from django.utils import timezone

from observation_portal.accounts.tasks import send_mail
from observation_portal.sciapplications.models import Call, ScienceApplication, ScienceCollaborationAllocation
from observation_portal.sciapplications.forms import (
    ScienceProposalAppForm, DDTProposalAppForm, KeyProjectAppForm, SciCollabAppForm, timerequest_formset, ci_formset
)

FORM_CLASSES = {
    'SCI': ScienceProposalAppForm,
    'DDT': DDTProposalAppForm,
    'KEY': KeyProjectAppForm,
    'NAOC': ScienceProposalAppForm,
    'COLAB': SciCollabAppForm
}


class SciApplicationCreateView(LoginRequiredMixin, CreateView):
    template_name = 'sciapplications/create.html'
    model = ScienceApplication

    def get_form_class(self):
        try:
            return FORM_CLASSES[self.call.proposal_type]
        except KeyError:
            raise Http404

    def get_success_url(self):
        if self.object.status == ScienceApplication.DRAFT:
            messages.add_message(self.request, messages.SUCCESS, _('Application created'))
            return reverse('sciapplications:update', kwargs={'pk': self.object.id})
        else:
            messages.add_message(self.request, messages.SUCCESS, _('Application successfully submitted'))
            if self.object.call.proposal_type == Call.DDT_PROPOSAL:
                ddt_submitted_email(self.object)
            return reverse('sciapplications:index')

    def get_initial(self):
        initial = {'call': self.call}
        # Fill in pi fields with submitter details since that is the most common use case for all forms,
        # except scicollab forms
        if self.call.proposal_type != Call.COLLAB_PROPOSAL:
            initial['pi'] = self.request.user.email
            initial['pi_first_name'] = self.request.user.first_name
            initial['pi_last_name'] = self.request.user.last_name
            initial['pi_institution'] = self.request.user.profile.institution
        return initial

    def get(self, request, *args, **kwargs):
        self.object = None
        self.call = get_object_or_404(Call, pk=kwargs['call'])
        if self.call.proposal_type == Call.COLLAB_PROPOSAL and \
                not ScienceCollaborationAllocation.objects.filter(admin=self.request.user).exists():
                raise Http404
        form = self.get_form()
        timerequest_form = timerequest_formset()
        ci_form = ci_formset()
        for ta_form in timerequest_form:
            ta_form.fields['instrument'].queryset = self.call.instruments.all()
        return self.render_to_response(
            self.get_context_data(form=form, timerequest_form=timerequest_form, call=self.call, ci_form=ci_form)
        )

    def post(self, request, *args, **kwargs):
        self.object = None
        self.call = get_object_or_404(Call, pk=kwargs['call'])
        if self.call.proposal_type == Call.COLLAB_PROPOSAL and \
                not ScienceCollaborationAllocation.objects.filter(admin=self.request.user).exists():
                raise Http404
        form = self.get_form()
        form.instance.submitter = request.user
        timerequest_form = timerequest_formset(self.request.POST)
        ci_form = ci_formset(self.request.POST)
        if form.is_valid() and timerequest_form.is_valid() and ci_form.is_valid():
            return self.forms_valid({'main': form, 'tr': timerequest_form, 'ci': ci_form})
        else:
            return self.forms_invalid({'main': form, 'tr': timerequest_form, 'ci': ci_form})

    def forms_valid(self, forms):
        self.object = forms['main'].save()
        if self.object.status == ScienceApplication.SUBMITTED:
            self.object.submitted = timezone.now()
            self.object.save()
        forms['tr'].instance = self.object
        forms['tr'].save()
        forms['ci'].instance = self.object
        forms['ci'].save()
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, forms):
        return self.render_to_response(
            self.get_context_data(form=forms['main'], timerequest_form=forms['tr'], ci_form=forms['ci'], call=self.call)
        )


class SciApplicationUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'sciapplications/create.html'

    def get_queryset(self):
        return ScienceApplication.objects.filter(submitter=self.request.user)

    def get_success_url(self):
        if self.object.status == ScienceApplication.DRAFT:
            messages.add_message(self.request, messages.SUCCESS, _('Application saved'))
            return reverse('sciapplications:update', kwargs={'pk': self.object.id})
        else:
            messages.add_message(self.request, messages.SUCCESS, _('Application successfully submitted'))
            if self.object.call.proposal_type == Call.DDT_PROPOSAL:
                ddt_submitted_email(self.object)

            return reverse('sciapplications:index')

    def get_form_class(self):
        return FORM_CLASSES[self.object.call.proposal_type]

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.status == ScienceApplication.DRAFT:
            raise Http404
        form = self.get_form()
        timerequest_form = timerequest_formset(instance=self.object)
        ci_form = ci_formset(instance=self.object)
        for ta_form in timerequest_form:
            ta_form.fields['instrument'].queryset = self.object.call.instruments.all()
        return self.render_to_response(
            self.get_context_data(form=form, timerequest_form=timerequest_form, ci_form=ci_form, call=self.object.call)
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        timerequest_form = timerequest_formset(self.request.POST, instance=self.object)
        ci_form = ci_formset(self.request.POST, instance=self.object)
        if form.is_valid() and timerequest_form.is_valid() and ci_form.is_valid():
            return self.forms_valid({'main': form, 'tr': timerequest_form, 'ci': ci_form})
        else:
            return self.forms_invalid({'main': form, 'tr': timerequest_form, 'ci': ci_form})

    def forms_valid(self, forms):
        self.object = forms['main'].save()
        if self.object.status == ScienceApplication.SUBMITTED:
            self.object.submitted = timezone.now()
            self.object.save()
        forms['tr'].instance = self.object
        forms['tr'].save()
        forms['ci'].instance = self.object
        forms['ci'].save()
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, forms):
        # The status is still DRAFT since the form is invalid
        data = forms['main'].data.copy()
        data['status'] = ScienceApplication.DRAFT
        forms['main'].data = data
        return self.render_to_response(
            self.get_context_data(
                form=forms['main'], timerequest_form=forms['tr'], ci_form=forms['ci'], call=self.object.call
            )
        )


class SciApplicationDetailView(LoginRequiredMixin, DetailView):
    model = ScienceApplication

    def get_queryset(self):
        if self.request.user.is_staff:
            return ScienceApplication.objects.all()
        else:
            return ScienceApplication.objects.filter(submitter=self.request.user)


class SciApplicationDeleteView(LoginRequiredMixin, DeleteView):
    model = ScienceApplication
    success_url = reverse_lazy('sciapplications:index')

    def get_queryset(self):
        return ScienceApplication.objects.filter(submitter=self.request.user, status=ScienceApplication.DRAFT)


class SciApplicationIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'sciapplications/index.html'

    def get_context_data(self):
        calls = Call.open_calls()
        draft_proposals = ScienceApplication.objects.filter(
            submitter=self.request.user, status=ScienceApplication.DRAFT
        ).order_by('tac_rank', '-call__semester', 'id')
        submitted_proposals = ScienceApplication.objects.filter(
            submitter=self.request.user
        ).exclude(status=ScienceApplication.DRAFT).order_by('tac_rank', '-call__semester', 'id')

        return {'calls': calls, 'draft_proposals': draft_proposals, 'submitted_proposals': submitted_proposals}


class SciApplicationPDFView(LoginRequiredMixin, DetailView):
    """Generate a pdf from the detailview, and append and file attachments to the end
    """
    model = ScienceApplication

    def get_queryset(self):
        if self.request.user.is_staff:
            return ScienceApplication.objects.all()
        else:
            return ScienceApplication.objects.filter(submitter=self.request.user)

    def render_to_response(self, context, **kwargs):
        context['pdf'] = True
        pdf_response = HttpResponse(content_type='application/pdf')
        response = super().render_to_response(context, **kwargs)
        response.render()
        try:
            pdf = self.object.generate_combined_pdf()
            pdf_response.write(pdf)
        except Exception as exc:
            error = 'There was an error generating your pdf. {}'
            messages.error(self.request, error.format(str(exc)))
            return HttpResponseRedirect(reverse('sciapplications:index'))
        return pdf_response


def ddt_submitted_email(sciproposal):
    message = render_to_string('sciapplications/ddt_submitted.txt', {'ddt': sciproposal})
    send_mail.send(
        'LCO Director\'s Discretionary Time Submission',
        message,
        'portal@lco.global',
        [sciproposal.submitter.email, 'ddt@lco.global']
    )
