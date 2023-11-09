from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.utils.functional import cached_property
from django.forms import model_to_dict
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.module_loading import import_string
from django.conf import settings
from collections import namedtuple

from urllib.parse import urljoin
import logging

from observation_portal.accounts.tasks import send_mail
from observation_portal.common.configdb import configdb

logger = logging.getLogger(__name__)


def proposal_as_dict(instance):
    proposal = model_to_dict(instance, exclude=['notes', 'users'])
    proposal['sca'] = instance.sca.id
    proposal['pis'] = [
        {
            'first_name': mem.user.first_name,
            'last_name': mem.user.last_name,
            'username': mem.user.username,
            'email': mem.user.email,
            'institution': mem.user.profile.institution
        } for mem in instance.membership_set.all() if mem.role == Membership.PI
    ]
    proposal['requestgroup_count'] = instance.requestgroup_set.count()
    proposal['coi_count'] = instance.membership_set.filter(role=Membership.CI).count()
    proposal['timeallocation_set'] = [ta.as_dict() for ta in instance.timeallocation_set.all()]
    return proposal


def timeallocation_as_dict(instance, exclude=None):
    if exclude is None:
        exclude = []
    time_allocation = model_to_dict(instance, exclude=exclude)
    return time_allocation


def membership_as_dict(instance):
    return {
        'username': instance.user.username,
        'first_name': instance.user.first_name,
        'last_name': instance.user.last_name,
        'email': instance.user.email,
        'role': instance.role,
        'proposal': instance.proposal.id,
        'time_limit': instance.time_limit,
        'time_used_by_user': instance.user.profile.time_used_in_proposal(instance.proposal),
        'simple_interface': instance.user.profile.simple_interface,
        'id': instance.id
    }


class Semester(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    start = models.DateTimeField()
    end = models.DateTimeField()
    proposals = models.ManyToManyField("Proposal", through="TimeAllocation")

    class Meta:
        ordering = ["-start", "id"]

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

    def time_requested_for_semester(self, semester, proposal_type):
        allocs = {ca.telescope_name: 0 for ca in self.collaborationallocation_set.all()}
        sciapp_filters = {'call__semester': semester, 'call__proposal_type': proposal_type}
        for sciapp in self.admin.scienceapplication_set.filter(**sciapp_filters):
            for telescope_name, time_requested in sciapp.time_requested_by_telescope_name.items():
                if telescope_name in allocs:
                    allocs[telescope_name] += time_requested
        return allocs

    def as_dict(self):
        return {
            'name': self.name,
            'id': self.id,
            'collaborationallocation_set': [alloc.as_dict() for alloc in self.collaborationallocation_set.all()]
        }


class CollaborationAllocation(models.Model):
    sca = models.ForeignKey(ScienceCollaborationAllocation, on_delete=models.CASCADE)
    telescope_name = models.CharField(max_length=255)
    allocation = models.FloatField(default=0)

    def __str__(self):
        return f'CollaborationAllocation for {self.sca.id}-{self.telescope_name}'

    def as_dict(self):
        return {
            'allocation': self.allocation,
            'telescope_name': self.telescope_name,
            'raw_telescope_name': configdb.get_raw_telescope_name(self.telescope_name)
        }


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
    tags = ArrayField(models.CharField(max_length=255), default=list, blank=True, help_text='List of strings tagging this proposal')

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
        return self.allocation(semester=self.current_semester)

    def allocation(self, semester):
        allocs = {}
        for ta in self.timeallocation_set.filter(semester=semester):
            instrument_types = ','.join(ta.instrument_types)
            allocs[instrument_types] = {
                'std': ta.std_allocation,
                'rr': ta.rr_allocation,
                'tc': ta.tc_allocation,
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
        # Only send reminders to non-education users
        if self.pi and not self.pi.profile.education_user:
            subject = _(f'Your {settings.ORGANIZATION_NAME} Time Allocation Summary')
            message = render_to_string(
                'proposals/timeallocationreminder.html',
                {
                    'proposal': self,
                    'allocations': self.timeallocation_set.filter(semester=self.current_semester),
                    'organization_name': settings.ORGANIZATION_NAME
                }
            )
            plain_message = strip_tags(message)

            send_mail.send(subject, plain_message, settings.ORGANIZATION_EMAIL, [self.pi.email], html_message=message)
        else:
            logger.warn('Proposal {} does not have a PI!'.format(self))

    def __str__(self):
        return self.id

    def as_dict(self):
        return import_string(settings.AS_DICT['proposals']['Proposal'])(self)


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
    instrument_types = ArrayField(base_field=models.CharField(max_length=200), default=list,
        help_text='One or more instrument_types to share this time allocation'
    )

    class Meta:
        ordering = ('-semester__id',)
        constraints = [
            models.UniqueConstraint(
                fields=['semester', 'proposal', 'instrument_types'],
                name='unique_proposal_semester_instrument_type_ta'
            )
        ]

    def __str__(self):
        return 'Timeallocation for {0}-{1}'.format(self.proposal, self.semester)

    def as_dict(self, exclude=None):
        return import_string(settings.AS_DICT['proposals']['TimeAllocation'])(self, exclude=exclude)

    def save(self, *args, **kwargs):
        tas_count = TimeAllocation.objects.filter(proposal=self.proposal, semester=self.semester,
                                                  instrument_types__overlap=self.instrument_types).exclude(
                                                      id=self.id).count()

        if tas_count > 0:
            # Don't save the time allocation in this case, because it is not a unique combination
            # of proposal, semester, and instrument_type
            return
        return super().save(*args, **kwargs)


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
        subject = _(f'You have been added to a proposal at {settings.ORGANIZATION_NAME}')
        message = render_to_string(
            'proposals/added.txt',
            {
                'proposal': self.proposal,
                'user': self.user,
                'organization_name': settings.ORGANIZATION_NAME,
                'observation_portal_base_url': settings.OBSERVATION_PORTAL_BASE_URL
            }
        )
        send_mail.send(subject, message, settings.ORGANIZATION_EMAIL, [self.user.email])

    def __str__(self):
        return '{0} {1} of {2}'.format(self.user, self.role, self.proposal)

    @property
    def time_limit_hours(self):
        return self.time_limit / 3600

    def as_dict(self):
        return import_string(settings.AS_DICT['proposals']['Membership'])(self)


class ProposalInvite(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    role = models.CharField(max_length=5, choices=Membership.ROLE_CHOICES)
    email = models.EmailField()
    sent = models.DateTimeField(null=True)
    used = models.DateTimeField(null=True)

    def __str__(self):
        return 'Invitation for {} token {}'.format(self.proposal, self.email)

    def accept(self, user):
        mem, _ = Membership.objects.get_or_create(
            proposal=self.proposal,
            user=user,
        )
        mem.role = self.role
        mem.save()

        self.used = timezone.now()
        self.save()

    def send_invitation(self):
        subject = _(f'You have been added to a proposal at {settings.ORGANIZATION_NAME}')
        message = render_to_string(
            'proposals/invitation.txt',
            {
                'proposal': self.proposal,
                'url': urljoin(reverse('registration_register'), f'?email={self.email}'),
                'organization_name': settings.ORGANIZATION_NAME,
                'observation_portal_base_url': settings.OBSERVATION_PORTAL_BASE_URL
            }
        )

        send_mail.send(subject, message, settings.ORGANIZATION_EMAIL, [self.email])
        self.sent = timezone.now()
        self.save()


class ProposalNotification(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return '{} - {}'.format(self.proposal, self.user)

    class Meta:
        unique_together = ('proposal', 'user')
