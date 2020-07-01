from datetime import datetime

from django.views import View
from django.views.generic.base import RedirectView
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.validators import validate_email
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse_lazy
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib import messages
from django_filters.views import FilterView
from django.utils.translation import ugettext as _
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.paginator import Paginator

from observation_portal.sciapplications.models import Call
from observation_portal.proposals.forms import ProposalNotificationForm
from observation_portal.proposals.models import Proposal, Membership, ProposalNotification, Semester, ProposalInvite
from observation_portal.proposals.filters import ProposalFilter, MembershipFilter

class ProposalDetailView(LoginRequiredMixin, DetailView):
    model = Proposal

    def get_queryset(self):
        if self.request.user.is_staff:
            qs = Proposal.objects.all()
        else:
            qs = self.request.user.proposal_set.all()
        return qs.prefetch_related('membership_set', 'membership_set__user__profile')

    def post(self, request, **kwargs):
        form = ProposalNotificationForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['notifications_enabled']:
                ProposalNotification.objects.get_or_create(user=request.user, proposal=self.get_object())
            else:
                ProposalNotification.objects.filter(user=request.user, proposal=self.get_object()).delete()
        messages.success(request, 'Preferences saved.')
        return HttpResponseRedirect(reverse('proposals:detail', kwargs={'pk': self.get_object().id}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enabled = ProposalNotification.objects.filter(user=self.request.user, proposal=self.get_object()).exists()
        context['notification_form'] = ProposalNotificationForm(initial={'notifications_enabled': enabled})
        # Paginate and allow fitering on CoI's as some proposals have a large number of them
        members_queryset = self.get_object().membership_set.filter(role=Membership.CI).order_by('id')
        members_filter = MembershipFilter(self.request.GET, queryset=members_queryset)
        paginate_by = 25
        members_paginator = Paginator(members_filter.qs, paginate_by)
        context['members_page'] = members_paginator.get_page(self.request.GET.get('ci_page'))
        context['members_filter'] = members_filter
        context['members_are_paginated'] = members_queryset.count() > paginate_by
        return context


class ProposalListView(LoginRequiredMixin, FilterView):
    filterset_class = ProposalFilter
    template_name = 'proposals/proposal_list.html'
    model = Proposal
    strict = False  # TODO remove when https://github.com/carltongibson/django-filter/issues/930 is fixed

    def get_queryset(self):
        return self.request.user.proposal_set.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['calls'] = Call.open_calls().exclude(proposal_type=Call.COLLAB_PROPOSAL)
        return context


class MembershipLimitView(LoginRequiredMixin, View):
    def post(self, request, **kwargs):
        membership = Membership.objects.get(pk=kwargs.get('pk'))
        if membership.proposal not in [m.proposal for m in request.user.membership_set.filter(role=Membership.PI)]:
            raise Http404
        try:
            time_limit = float(request.POST['time_limit']) * 3600
        except ValueError:
            messages.error(request, 'Please enter a valid time limit')
        else:
            membership.time_limit = time_limit
            membership.save()
            messages.success(request, 'Time limit for {0} {1} set to {2} hours'.format(
                membership.user.first_name, membership.user.last_name, membership.time_limit / 3600
            ))
        return HttpResponseRedirect(reverse('proposals:detail', kwargs={'pk': membership.proposal.id}))


class GlobalMembershipLimitView(LoginRequiredMixin, View):
    def post(self, request, **kwargs):
        try:
            proposal = request.user.membership_set.get(proposal=kwargs.get('pk'), role=Membership.PI).proposal
        except Membership.DoesNotExist:
            raise Http404
        try:
            time_limit = float(request.POST['time_limit']) * 3600
        except ValueError:
            messages.error(request, 'Please enter a valid time limit')
        else:
            proposal.membership_set.filter(role=Membership.CI).update(time_limit=time_limit)
            messages.success(request, 'All CI time limits set to {0} hours'.format(time_limit / 3600))
        return HttpResponseRedirect(reverse('proposals:detail', kwargs={'pk': proposal.id}))


class InviteCreateView(LoginRequiredMixin, View):
    def post(self, request, **kwargs):
        try:
            proposal = request.user.membership_set.get(proposal=kwargs.get('pk'), role=Membership.PI).proposal
        except Membership.DoesNotExist:
            raise Http404
        emails = request.POST['email'].replace(' ', '').strip(',').split(',')
        valid = True
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                valid = False
                messages.error(request, _(f'Please enter a valid email address: {email}'))
            if email.lower() == request.user.email.lower():
                messages.error(request, f'You cannot invite yourself ({email}) to be a Co-Investigator')
                valid = False
        if valid:
            proposal.add_users(emails, Membership.CI)
            messages.success(request, _('Co Investigator(s) invited'))
        return HttpResponseRedirect(reverse('proposals:detail', kwargs={'pk': proposal.id}))


class ProposalInviteDeleteView(LoginRequiredMixin, DeleteView):
    model = ProposalInvite

    def get_success_url(self):
        return reverse_lazy('proposals:detail', kwargs={'pk': self.get_object().proposal.id})

    def get_queryset(self):
        proposals = self.request.user.proposal_set.filter(membership__role=Membership.PI)
        return ProposalInvite.objects.filter(proposal__in=proposals)


class MembershipDeleteView(LoginRequiredMixin, DeleteView):
    model = Membership

    def get_success_url(self):
        return reverse_lazy('proposals:detail', kwargs={'pk': self.get_object().proposal.id})

    def get_queryset(self):
        proposals = self.request.user.proposal_set.filter(membership__role=Membership.PI)
        return Membership.objects.filter(proposal__in=proposals)


class SemesterDetailView(DetailView):
    model = Semester

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['proposals'] = self.get_object().proposals.filter(active=True, non_science=False) \
            .distinct().order_by('sca__name')
        return context


class SemesterAdminView(UserPassesTestMixin, DetailView):
    model = Semester
    template_name = 'proposals/semester_admin.html'

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['semesters'] = Semester.objects.all().order_by('-start')
        return context

class CurrentSemesterRedirect(RedirectView):
    permanent = False
    pattern_name = 'proposals:semester-detail'

    def get_redirect_url(self, *args, **kwargs):
        now = datetime.utcnow()
        semesters = Semester.objects.filter(start__lte=now, end__gte=now)
        try:
            return reverse(self.pattern_name, kwargs={'pk':semesters[0].id})
        except IndexError:
            return reverse('proposals:list')
