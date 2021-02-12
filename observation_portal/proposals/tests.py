from django.test import TestCase
from django.core import mail
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone
from mixer.backend.django import mixer
import datetime
from django_dramatiq.test import DramatiqTestCase

from observation_portal.proposals.models import ProposalInvite, Proposal, Membership, ProposalNotification, TimeAllocation, Semester
from observation_portal.requestgroups.models import RequestGroup, Configuration, InstrumentConfig
from observation_portal.accounts.models import Profile
from observation_portal.common.test_helpers import create_simple_requestgroup
from observation_portal.proposals.tasks import time_allocation_reminder
from observation_portal.requestgroups.signals import handlers  # DO NOT DELETE, needed to active signals


class TestProposal(DramatiqTestCase):
    def test_add_existing_user(self):
        proposal = mixer.blend(Proposal)
        user = mixer.blend(User, email='email1@lcogt.net')
        emails = ['email1@lcogt.net']
        proposal.add_users(emails, Membership.CI)

        self.broker.join("default")
        self.worker.join()

        self.assertIn(proposal, user.proposal_set.all())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(proposal.title, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [user.email])

    def test_add_nonexisting_user(self):
        proposal = mixer.blend(Proposal)
        emails = ['email1@lcogt.net']
        proposal.add_users(emails, Membership.CI)
        self.assertFalse(proposal.users.count())
        self.assertTrue(ProposalInvite.objects.filter(email='email1@lcogt.net').exists())

    def test_add_nonexisting_user_twice(self):
        proposal = mixer.blend(Proposal)
        proposal_invite = mixer.blend(ProposalInvite, proposal=proposal, role=Membership.CI)
        proposal.add_users([proposal_invite.email], Membership.CI)
        self.assertEqual(ProposalInvite.objects.filter(email=proposal_invite.email).count(), 1)

    def test_no_dual_membership(self):
        proposal = mixer.blend(Proposal)
        user = mixer.blend(User)
        Membership.objects.create(user=user, proposal=proposal, role=Membership.PI)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=user, proposal=proposal, role=Membership.CI)

    def test_user_already_member(self):
        proposal = mixer.blend(Proposal)
        user = mixer.blend(User)
        mixer.blend(Membership, proposal=proposal, user=user, role=Membership.CI)
        proposal.add_users([user.email], Membership.CI)
        self.assertIn(proposal, user.proposal_set.all())
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_create_duplicate_time_allocations(self):
        proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester)
        instrument_type = 'instrument_a'
        TimeAllocation.objects.create(proposal=proposal, semester=semester, instrument_type=instrument_type)
        with self.assertRaises(IntegrityError):
            TimeAllocation.objects.create(proposal=proposal, semester=semester, instrument_type=instrument_type)

    def test_can_create_many_timeallocations_that_arent_duplicates(self):
        expected_timeallocations_count = 2
        proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester)
        for i in range(expected_timeallocations_count):
            TimeAllocation.objects.create(proposal=proposal, semester=semester, instrument_type=f'instrument_{i}')
        self.assertEqual(TimeAllocation.objects.count(), expected_timeallocations_count)


class TestProposalInvitation(DramatiqTestCase):
    def test_send_invitation(self):
        invitation = mixer.blend(ProposalInvite)
        invitation.send_invitation()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invitation.proposal.id, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [invitation.email])

    def test_accept(self):
        invitation = mixer.blend(ProposalInvite)
        user = mixer.blend(User)
        invitation.accept(user)
        self.assertIn(invitation.proposal, user.proposal_set.all())


class TestProposalNotifications(DramatiqTestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.user = mixer.blend(User)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.requestgroup = mixer.blend(RequestGroup, proposal=self.proposal, submitter=self.user, state='PENDING',
                                        observation_type=RequestGroup.NORMAL)

    def test_all_proposal_notification(self):
        mixer.blend(Profile, user=self.user, notifications_enabled=True)
        download_urls = ['http://download_data/?requestgroup={requestgroup_id}', 'http://download_data/', '']
        for download_url in download_urls:
            download_url_is_in_email = download_url != ''
            complete_download_url = download_url.format(requestgroup_id=self.requestgroup.id)
            with self.subTest(download_url=download_url):
                with self.settings(REQUESTGROUP_DATA_DOWNLOAD_URL=download_url):
                    mail.outbox = []
                    self.requestgroup.state = 'COMPLETED'
                    self.requestgroup.save()

                    self.broker.join("default")
                    self.worker.join()

                    self.assertEqual(len(mail.outbox), 1)
                    self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
                    if download_url_is_in_email:
                        self.assertIn('Data may be downloaded here', str(mail.outbox[0].message()))
                        self.assertIn(complete_download_url, str(mail.outbox[0].message()))
                    else:
                        self.assertNotIn('Data may be downloaded here', str(mail.outbox[0].message()))
                    self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_single_proposal_notification(self):
        mixer.blend(Profile, user=self.user, notifications_enabled=False)
        mixer.blend(ProposalNotification, user=self.user, proposal=self.proposal)
        self.requestgroup.state = 'COMPLETED'
        self.requestgroup.save()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_user_loves_notifications(self):
        mixer.blend(Profile, user=self.user, notifications_enabled=True)
        mixer.blend(ProposalNotification, user=self.user, proposal=self.proposal)
        self.requestgroup.state = 'COMPLETED'
        self.requestgroup.save()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_notifications_only_authored(self):
        mixer.blend(Profile, user=self.user, notifications_enabled=True, notifications_on_authored_only=True)
        self.requestgroup.submitter = self.user
        self.requestgroup.state = 'COMPLETED'
        self.requestgroup.save()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_no_notifications_only_authored(self):
        mixer.blend(Profile, user=self.user, notifications_enabled=True, notifications_on_authored_only=True)
        self.requestgroup.submitter = mixer.blend(User)
        self.requestgroup.state = 'COMPLETED'
        self.requestgroup.save()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)

    def test_no_notifications(self):
        self.requestgroup.state = 'COMPLETED'
        self.requestgroup.save()

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)


class TestTimeAllocationEmail(DramatiqTestCase):
    def setUp(self):
        super().setUp()
        self.pi = mixer.blend(User)
        self.coi = mixer.blend(User)
        self.proposal = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, user=self.pi, proposal=self.proposal, role='PI')
        mixer.blend(Membership, user=self.coi, proposal=self.proposal, role='CI')
        now = timezone.now()
        self.current_semester = mixer.blend(
            Semester, start=now, end=now + datetime.timedelta(days=30))

        self.future_semester = mixer.blend(
            Semester, start=now + datetime.timedelta(days=30), end=now + datetime.timedelta(days=60)
        )

    def test_sends_email_to_pi_for_current_active_proposal(self):
        mixer.blend(TimeAllocation, proposal=self.proposal, semester=self.current_semester)
        time_allocation_reminder()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.proposal.id, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.pi.email])

    def test_does_not_send_email_for_active_proposal_with_no_current_allocations(self):
        mixer.blend(TimeAllocation, proposal=self.proposal, semester=self.future_semester)
        time_allocation_reminder()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_email_for_inactive_proposal(self):
        mixer.blend(TimeAllocation, proposal=self.proposal, semester=self.current_semester)
        self.proposal.active = False
        self.proposal.save()
        time_allocation_reminder()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)


class TestProposalUserLimits(TestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester, start=timezone.now(), end=timezone.now() + datetime.timedelta(days=180))
        mixer.blend(TimeAllocation, proposal=self.proposal, semester=semester)
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
        mixer.blend(Membership, user=self.user, proposal=self.proposal, role=Membership.CI)

    def test_time_used_for_user(self):
        self.assertEqual(self.user.profile.time_used_in_proposal(self.proposal), 0)
        configuration = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG')
        instrument_config = mixer.blend(InstrumentConfig, configuration=configuration, exposure_time=30)
        create_simple_requestgroup(self.user, self.proposal, configuration=configuration,
                                   instrument_config=instrument_config)
        self.assertGreater(self.user.profile.time_used_in_proposal(self.proposal), 0)


class TestDefaultIPP(TestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.semester = mixer.blend(Semester)

    def test_default_ipp_time_is_set(self):
        ta = TimeAllocation(semester=self.semester, proposal=self.proposal, std_allocation=100)
        ta.save()
        self.assertEqual(ta.ipp_limit, 10)
        self.assertEqual(ta.ipp_time_available, 5)

    def test_default_ipp_time_is_not_set(self):
        ta = TimeAllocation(
            semester=self.semester, proposal=self.proposal, std_allocation=100, ipp_limit=99, ipp_time_available=42
        )
        ta.save()
        self.assertEqual(ta.ipp_limit, 99)
        self.assertEqual(ta.ipp_time_available, 42)

    def test_default_ipp_set_only_on_creation(self):
        ta = TimeAllocation(semester=self.semester, proposal=self.proposal, std_allocation=100)
        ta.save()
        ta.ipp_time_available = 0
        ta.save()
        self.assertEqual(ta.ipp_time_available, 0)


class TestProposalAdmin(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(self.admin_user)
        self.proposals = mixer.cycle(3).blend(Proposal, active=False)

    def test_activate_selected(self):
        self.client.post(
            reverse('admin:proposals_proposal_changelist'),
            data={'action': 'activate_selected', '_selected_action': [str(proposal.pk) for proposal in self.proposals]},
            follow=True
        )
        for proposal in self.proposals:
            self.assertEqual(Proposal.objects.get(pk=proposal.id).active, True)
