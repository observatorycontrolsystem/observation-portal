import smtplib
from collections import defaultdict
from urllib.parse import urljoin

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.translation import gettext as _
from django.contrib.postgres.fields import ArrayField
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.conf import settings

from observation_portal.common.configdb import configdb
from observation_portal.accounts.tasks import send_mail
from observation_portal.proposals.models import (
    Semester, TimeAllocation, Proposal, ScienceCollaborationAllocation, Membership
)


class NoTimeAllocatedError(Exception):
    pass


class MultipleTimesAllocatedError(Exception):
    pass


class Instrument(models.Model):
    code = models.CharField(max_length=50)
    display = models.CharField(max_length=50)

    class Meta:
        ordering = ["code"]

    @cached_property
    def telescope_name(self):
        instrument_type_to_telescope_name = configdb.get_telescope_name_by_instrument_types(exclude_states=['DISABLED'])
        return instrument_type_to_telescope_name.get(self.code.upper(), '')

    def __str__(self):
        return self.display

    def as_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.display,
            'telescope_name': self.telescope_name
        }


class Call(models.Model):
    SCI_PROPOSAL = 'SCI'
    DDT_PROPOSAL = 'DDT'
    KEY_PROPOSAL = 'KEY'
    NAOC_PROPOSAL = 'NAOC'
    COLLAB_PROPOSAL = 'COLAB'

    PROPOSAL_TYPE_CHOICES = (
        (SCI_PROPOSAL, 'Science'),
        (DDT_PROPOSAL, 'Director\'s Discretionary Time'),
        (KEY_PROPOSAL, 'Key Project'),
        (NAOC_PROPOSAL, 'NAOC proposal'),
        (COLLAB_PROPOSAL, 'Science Collaboration Proposal')
    )

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    opens = models.DateTimeField()
    deadline = models.DateTimeField()
    call_url = models.URLField(blank=True, default='')
    # TODO does this need to be a model itself?
    instruments = models.ManyToManyField(Instrument)
    proposal_type = models.CharField(max_length=5, choices=PROPOSAL_TYPE_CHOICES)
    eligibility = models.TextField(blank=True, default='')
    eligibility_short = models.TextField(blank=True, default='')

    @classmethod
    def open_calls(cls):
        return cls.objects.filter(opens__lte=timezone.now(), deadline__gte=timezone.now())

    @property
    def eligible_semesters(self):
        # List of semesters for which time can be requested for this call
        if self.proposal_type == Call.KEY_PROPOSAL:
            return [semester.id for semester in Semester.future_semesters()]
        else:
            return [self.semester.id]

    def __str__(self):
        return '{0} call for {1}'.format(self.get_proposal_type_display(), self.semester)


def pdf_upload_path(instance, filename):
    # PDFs will be uploaded to MEDIA_ROOT/sciapps/<semester>/
    return 'sciapps/{0}/{1}/{2}'.format(instance.call.semester.id, instance.id, filename)


class ScienceApplication(models.Model):
    DRAFT = 'DRAFT'
    SUBMITTED = 'SUBMITTED'
    ACCEPTED = 'ACCEPTED'
    REJECTED = 'REJECTED'
    PORTED = 'PORTED'

    STATUS_CHOICES = (
        (DRAFT, 'Draft'),
        (SUBMITTED, 'Submitted'),
        (ACCEPTED, 'Accepted'),
        (REJECTED, 'Rejected'),
        (PORTED, 'Ported')
    )

    title = models.CharField(max_length=200)
    call = models.ForeignKey(Call, on_delete=models.CASCADE)
    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    abstract = models.TextField(blank=True, default='')
    pi = models.EmailField(blank=True, default='')
    pi_first_name = models.CharField(max_length=255, blank=True, default='', help_text='')
    pi_last_name = models.CharField(max_length=255, blank=True, default='', help_text='')
    pi_institution = models.CharField(max_length=255, blank=True, default='', help_text='')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_CHOICES[0][0])
    proposal = models.ForeignKey(Proposal, null=True, blank=True, on_delete=models.SET_NULL)
    tac_rank = models.PositiveIntegerField(default=0)
    tac_priority = models.PositiveIntegerField(default=0)
    pdf = models.FileField(upload_to=pdf_upload_path, blank=True, null=True)
    tags = ArrayField(models.CharField(max_length=255), default=list, blank=True, help_text='List of strings tagging this application')

    # Admin only Notes
    notes = models.TextField(blank=True, default='', help_text='Add notes here. Not visible to users.')

    # Misc
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    submitted = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-id',)

    def __str__(self):
        return self.title

    @property
    def sca(self):
        try:
            return self.submitter.sciencecollaborationallocation
        except ScienceCollaborationAllocation.DoesNotExist:
            return ScienceCollaborationAllocation.objects.get_or_create(id='LCO')[0]

    @property
    def proposal_code(self):
        proposal_type_to_name = {
            'SCI': 'LCO',
            'KEY': 'KEY',
            'DDT': 'DDT',
            'NAOC': 'NAOC',
            'COLAB': self.sca.id
        }
        return '{0}{1}-{2}'.format(
            proposal_type_to_name[self.call.proposal_type], self.call.semester, str(self.tac_rank).zfill(3)
        )

    @property
    def time_requested_by_telescope_name(self):
        time_by_telescope_name = defaultdict(int)
        for timerequest in self.timerequest_set.all():
            telescope_names = set()
            for instrument_type in timerequest.instrument_types.all():
                # Use a set to make sure we only add once per telescope class here
                telescope_names.add(instrument_type.telescope_name)
            for telescope_name in telescope_names:
                time_by_telescope_name[telescope_name] += timerequest.total_requested_time
        return time_by_telescope_name

    def get_absolute_url(self):
        if settings.SCIENCE_APPLICATION_DETAIL_URL:
            return settings.SCIENCE_APPLICATION_DETAIL_URL.format(sciapp_id=self.id)
        else:
            return reverse('api:scienceapplications-detail', args=(self.id,))

    def convert_to_proposal(self):
        approved_time_requests = self.timerequest_set.filter(approved=True)
        if not approved_time_requests.count():
            raise NoTimeAllocatedError

        unique_time_requests = set()
        for tr in approved_time_requests:
            unique_time_requests.add(f'{tr.semester.id}-{",".join([it.code for it in tr.instrument_types.all()])}')
        if approved_time_requests.count() != len(unique_time_requests):
            raise MultipleTimesAllocatedError

        proposal = Proposal.objects.create(
            id=self.proposal_code,
            title=self.title,
            abstract=self.abstract,
            tac_priority=self.tac_priority,
            tac_rank=self.tac_rank,
            active=False,
            sca=self.sca,
            tags=self.tags
        )

        for tr in self.timerequest_set.filter(approved=True):
            TimeAllocation.objects.create(
                std_allocation=tr.std_time,
                rr_allocation=tr.rr_time,
                tc_allocation=tr.tc_time,
                instrument_types=[it.code for it in tr.instrument_types.all()],
                semester=tr.semester,
                proposal=proposal
            )

        # Send invitations if necessary. The check is done because the pi field may not be set at this point,
        # making the submitter the PI on the proposal by default.
        if self.pi:
            proposal.add_users([self.pi], Membership.PI)
        else:
            Membership.objects.create(proposal=proposal, user=self.submitter, role=Membership.PI)

        proposal.add_users([coi.email for coi in self.coinvestigator_set.all()], Membership.CI)

        self.proposal = proposal
        self.status = ScienceApplication.PORTED
        self.save()
        return proposal

    def send_approved_notification(self):
        subject = _(f'Your proposal at {settings.ORGANIZATION_NAME} has been approved')
        message = render_to_string(
            'sciapplications/approved.txt',
            {
                'proposal': self.proposal,
                'semester': self.call.semester,
                'semester_already_started': self.call.semester.start < timezone.now(),
                'organization_name': settings.ORGANIZATION_NAME,
                'observation_portal_base_url': settings.OBSERVATION_PORTAL_BASE_URL
            }
        )
        # Find the email to send the notification to. The proposal will have been created at this point, but the pi on
        # the proposal might not be set yet if the pi has not a registered an account. In that case, use the email
        # as set on the science application.
        pi_email = self.proposal.pi.email if self.proposal.pi else self.pi
        email_sent = True
        try:
            send_mail.send(subject, message, settings.ORGANIZATION_EMAIL, [pi_email])
        except smtplib.SMTPException:
            email_sent = False
        return email_sent


class TimeRequest(models.Model):
    science_application = models.ForeignKey(ScienceApplication, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    instrument_types = models.ManyToManyField(Instrument, related_name='timerequests')
    std_time = models.PositiveIntegerField(default=0)
    rr_time = models.PositiveIntegerField(default=0)
    tc_time = models.PositiveIntegerField(default=0)
    approved = models.BooleanField(default=False)

    class Meta:
        ordering = ('semester',)

    @property
    def total_requested_time(self):
        return sum([self.std_time, self.rr_time, self.tc_time])

    def __str__(self):
        return '{} {} TimeRequest'.format(self.science_application, ','.join([it.code for it in self.instrument_types.all()]))


class CoInvestigator(models.Model):
    science_application = models.ForeignKey(ScienceApplication, on_delete=models.CASCADE)
    email = models.EmailField()
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    institution = models.CharField(max_length=255)

    class Meta:
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return '{0} {1} <{2}> ({3})'.format(self.first_name, self.last_name, self.email, self.institution)


class ReviewPanel(models.Model):
    name = models.CharField(max_length=128)

    members = models.ManyToManyField(User, related_name="review_panels", through="ReviewPanelMembership")

    def __str__(self):
        return f"{self.name!s}"


class ReviewPanelMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    review_panel = models.ForeignKey(ReviewPanel, on_delete=models.CASCADE)


class ScienceApplicationReview(models.Model):
    science_application = models.OneToOneField(ScienceApplication, on_delete=models.CASCADE, related_name="review")

    review_panel = models.ForeignKey(ReviewPanel, on_delete=models.CASCADE, related_name="science_application_reviews")

    primary_reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="primary_reviewer_for", help_text="Primary reviewer")

    secondary_reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="secondary_reviewer_for", help_text="Secondary reviewer")

    created_at = models.DateTimeField(auto_now_add=True)

    class ScienceCategory(models.TextChoices):
        EXPLOSIVE_TRANSIENTS = "EXPLOSIVE_TRANSIENTS", _("Explosive Transients")
        ACTIVE_GALAXIES = "ACTIVE_GALAXIES", _("Active Galaxies")
        STARS_STELLAR_ACTIVITY = "STARS_STELLAR_ACTIVITY", _("Stars and Stellar Activity")
        SOLAR_SYSTEM_SMALL_BODIES = "SOLAR_SYSTEM_SMALL_BODIES", _("Solar System Small Bodies")
        MISCELLANEOUS = "MISC", _("Miscellaneous")
        EXOPLANETS = "EXOPLANETS", _("Exoplanets")

    science_category = models.CharField(choices=ScienceCategory.choices, default=ScienceCategory.MISCELLANEOUS, max_length=255)

    technical_review = models.TextField(blank=True, default="")

    class Status(models.TextChoices):
        AWAITING_REVIEWS = "AWAITING_REVIEWS", _("Awaiting Reviews")
        PANEL_DISCUSSION = "PANEL_DISCUSSION", _("Panel Discussion")
        ACCEPTED = "ACCEPTED", _("Accepted")
        REJECTED = "REJECTED", _("Rejected")

    status = models.CharField(choices=Status.choices, default=Status.AWAITING_REVIEWS, max_length=255)

    summary = models.TextField(blank=True, default="")

    mean_grade = models.DecimalField(
        blank=True, null=True, default=None, max_digits=4, decimal_places=2,
        help_text="Mean of all user reviews. This field is automatically recalculated anytime a user review is added/updated/deleted"
    )

    notify_submitter = models.BooleanField(
        default=False,
        help_text="Whether to send the application submitter notifications regarding the acceptance or rejection of this review."
    )

    notify_submitter_additional_message = models.TextField(
        blank=True,
        default="",
        help_text="Additional message to embed in notifications sent to the application submitter."
    )


    def __str__(self):
        return f"{self.science_application!s} review"

    def save(self, *args, **kwargs):
        # created
        if not self.pk:
            r =  super().save(*args, **kwargs)
            self.send_review_requested_email_to_all_panelists()
            return r

        if self.status == ScienceApplicationReview.Status.ACCEPTED:
            self.science_application.status = ScienceApplication.ACCEPTED
        elif self.status == ScienceApplicationReview.Status.REJECTED:
            self.science_application.status = ScienceApplication.REJECTED
        else:
            return super().save(*args, **kwargs)

        r = super().save(*args, **kwargs)
        self.science_application.save()

        if self.notify_submitter:
            self.send_review_accepted_or_rejected_email_to_submitter()

        return r

    def send_review_requested_email_to_all_panelists(self):
        subject = str(_(f"Proposal Application Review Requested: {self.science_application.title}"))
        for x in self.review_panel.members.all():
            message = render_to_string(
                "sciapplications/review_requested.txt",
                {
                    "panelist": x,
                    "science_application": self.science_application,
                    "organization_name": settings.ORGANIZATION_NAME,
                    "review_url": urljoin(settings.OBSERVATION_PORTAL_BASE_URL, f"proposal-reviews/{self.pk}/my-review"),
                }
            )
            send_mail.send(subject, message, settings.ORGANIZATION_EMAIL, [str(x.email)])

    def send_review_accepted_or_rejected_email_to_submitter(self):
        if self.status == ScienceApplicationReview.Status.ACCEPTED:
            status = "accepted"
        elif self.status == ScienceApplicationReview.Status.REJECTED:
            status = "rejected"
        else:
            raise Exception("invalid state")

        subject = str(_(f"Proposal Application {status.capitalize()}: {self.science_application.title}"))
        submitter = self.science_application.submitter

        message = render_to_string(
            "sciapplications/review_accepted_or_rejected.txt",
            {
                "submitter": submitter,
                "science_application": self.science_application,
                "status": status,
                "additional_message": self.notify_submitter_additional_message,
                "organization_name": settings.ORGANIZATION_NAME,
            }
        )
        send_mail.send(subject, message, settings.ORGANIZATION_EMAIL, [str(submitter.email)])


class ScienceApplicationUserReview(models.Model):
    science_application_review = models.ForeignKey(ScienceApplicationReview, on_delete=models.CASCADE, related_name="user_reviews")

    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sciapplication_reviews")

    comments = models.TextField(blank=True, default="")

    finished = models.BooleanField(default=False)

    grade = models.DecimalField(blank=True, null=True, default=None, max_digits=4, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["science_application_review", "reviewer"], name="%(app_label)s_%(class)s_primary_key"),
        ]


    def __str__(self):
        return f"{self.reviewer!s}'s {self.science_application_review!s}"
