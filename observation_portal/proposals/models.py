from django.contrib.auth.models import User
from django.utils.functional import cached_property
from django.forms import model_to_dict
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from collections import namedtuple
import logging

from observation_portal.accounts.tasks import send_mail

logger = logging.getLogger(__name__)


class Semester(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    start = models.DateTimeField()
    end = models.DateTimeField()
    proposals = models.ManyToManyField("Proposal", through="TimeAllocation")

    @classmethod
    def current_semesters(cls, future=False):
        semesters = cls.objects.filter(end__gte=timezone.now())
        if not future:
            semesters = semesters.filter(start__lte=timezone.now())
        return semesters

    @classmethod
    def future_semesters(cls):
        return cls.objects.filter(start__gt=timezone.now())

    def __str__(self):
        return self.id


class ScienceCollaborationAllocation(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255, blank=True, default='')
    admin = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.id

    def time_requested_for_semester(self, semester):
        allocs = {ca.telescope_name: 0 for ca in self.collaborationallocation_set.all()}
        for sciapp in self.admin.scienceapplication_set.filter(call__semester=semester, call__proposal_type='COLAB'):
            for k, v in sciapp.time_requested_by_telescope_name.items():
                if k in allocs:
                    allocs[k] += v
        return allocs


class CollaborationAllocation(models.Model):
    sca = models.ForeignKey(ScienceCollaborationAllocation, on_delete=models.CASCADE)
    telescope_name = models.CharField(max_length=255)
    allocation = models.FloatField(default=0)

    def __str__(self):
        return f'CollaborationAllocation for {self.sca.id}-{self.telescope_name}'


class Proposal(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    active = models.BooleanField(default=True)
    title = models.CharField(max_length=255, default='', blank=True)
    abstract = models.TextField(default='', blank=True)
    tac_priority = models.PositiveIntegerField(default=0)
    tac_rank = models.PositiveIntegerField(default=0)
    sca = models.ForeignKey(ScienceCollaborationAllocation, on_delete=models.CASCADE)
    public = models.BooleanField(default=False)
    non_science = models.BooleanField(default=False)
    direct_submission = models.BooleanField(default=False)
    users = models.ManyToManyField(User, through='Membership')

    # Admin only notes
    notes = models.TextField(blank=True, default='', help_text='Add notes here. Not visible to users.')

    # Misc
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('title',)

    @cached_property
    def pi(self):
        return self.users.filter(membership__role=Membership.PI).first()

    @cached_property
    def cis(self):
        return self.users.filter(membership__role=Membership.CI)

    @cached_property
    def current_semester(self):
        return self.semester_set.intersection(Semester.current_semesters()).first()

    @cached_property
    def current_allocation(self):
        allocs = {}
        for ta in self.timeallocation_set.filter(semester=self.current_semester):
            allocs[ta.instrument_type.replace('-', '')] = {
                'std': ta.std_allocation,
                'std_used': ta.std_time_used,
                'rr': ta.rr_allocation,
                'rr_used': ta.rr_time_used,
                'tc': ta.tc_allocation,
                'tc_used': ta.tc_time_used
            }
        return allocs

    @classmethod
    def current_proposals(cls):
        return cls.objects.filter(semester__in=Semester.current_semesters(future=True))

    def add_users(self, emails, role):
        for email in emails:
            if User.objects.filter(email=email).exists():
                membership, created = Membership.objects.get_or_create(
                    proposal=self,
                    user=User.objects.get(email=email),
                    role=role
                )
                if created:
                    membership.send_notification()
            else:
                proposal_invite, created = ProposalInvite.objects.get_or_create(
                    proposal=self,
                    role=role,
                    email=email
                )
                proposal_invite.send_invitation()

        logger.info('Users added to proposal {0}: {1}'.format(self, emails))

    def send_time_allocation_reminder(self):
        if self.pi:
            subject = _('Your LCO Time Allocation Summary')
            message = render_to_string(
                'proposals/timeallocationreminder.html',
                {
                    'proposal': self,
                    'allocations': self.timeallocation_set.filter(semester=self.current_semester)
                }
            )
            plain_message = strip_tags(message)

            send_mail.send(subject, plain_message, 'science-support@lco.global', [self.pi.email], html_message=message)
        else:
            logger.warn('Proposal {} does not have a PI!'.format(self))

    def __str__(self):
        return self.id

    def as_dict(self):
        proposal = model_to_dict(self, exclude=[])
        proposal['sca'] = self.sca.id
        proposal['timeallocation_set'] = [ta.as_dict() for ta in self.timeallocation_set.all()]
        proposal['users'] = {
            mem.user.username: {
                'first_name': mem.user.first_name,
                'last_name': mem.user.last_name,
                'time_limit': mem.time_limit
            } for mem in self.membership_set.all()
        }
        return proposal


TimeAllocationKey = namedtuple('TimeAllocationKey', ['semester', 'instrument_type'])


class TimeAllocation(models.Model):
    ipp_limit = models.FloatField(default=0)
    ipp_time_available = models.FloatField(default=0)
    std_allocation = models.FloatField(default=0)
    std_time_used = models.FloatField(default=0)
    rr_allocation = models.FloatField(default=0)
    rr_time_used = models.FloatField(default=0)
    tc_allocation = models.FloatField(default=0)
    tc_time_used = models.FloatField(default=0)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    instrument_type = models.CharField(max_length=200)

    class Meta:
        ordering = ('-semester__id',)

    def __str__(self):
        return 'Timeallocation for {0}-{1}'.format(self.proposal, self.semester)

    def as_dict(self):
        time_allocation = model_to_dict(self, exclude=[])
        return time_allocation


class Membership(models.Model):
    PI = 'PI'
    CI = 'CI'
    ROLE_CHOICES = (
        (PI, 'Principal Investigator'),
        (CI, 'Co-Investigator')
    )

    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=5, choices=ROLE_CHOICES)
    time_limit = models.IntegerField(default=-1)  # seconds, -1 is unlimited

    class Meta:
        unique_together = ('user', 'proposal')

    def send_notification(self):
        subject = _('You have been added to a proposal at LCO.global')
        message = render_to_string(
            'proposals/added.txt',
            {
                'proposal': self.proposal,
                'user': self.user,
            }
        )
        send_mail.send(subject, message, 'portal@lco.global', [self.user.email])

    def __str__(self):
        return '{0} {1} of {2}'.format(self.user, self.role, self.proposal)

    @property
    def time_limit_hours(self):
        return self.time_limit / 3600


class ProposalInvite(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    role = models.CharField(max_length=5, choices=Membership.ROLE_CHOICES)
    email = models.EmailField()
    sent = models.DateTimeField(null=True)
    used = models.DateTimeField(null=True)

    def __str__(self):
        return 'Invitation for {} token {}'.format(self.proposal, self.email)

    def accept(self, user):
        Membership.objects.create(
            proposal=self.proposal,
            role=self.role,
            user=user,
        )
        self.used = timezone.now()
        self.save()

    def send_invitation(self):
        subject = _('You have been added to a proposal at LCO.global')
        message = render_to_string(
            'proposals/invitation.txt',
            {
                'proposal': self.proposal,
                'url': reverse('registration_register')
            }
        )

        send_mail.send(subject, message, 'portal@lco.global', [self.email])
        self.sent = timezone.now()
        self.save()


class ProposalNotification(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return '{} - {}'.format(self.proposal, self.user)

    class Meta:
        unique_together = ('proposal', 'user')
