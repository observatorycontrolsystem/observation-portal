from django.test import TestCase
from django.core import mail
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from mixer.backend.django import mixer
from django_dramatiq.test import DramatiqTestCase

from observation_portal.proposals.models import Semester, Proposal
from observation_portal.sciapplications.models import ScienceApplication, Call, Instrument, TimeRequest


class TestSciAppAdmin(DramatiqTestCase):
    def setUp(self):
        self.semester = mixer.blend(Semester)
        self.user = mixer.blend(User)
        self.admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(self.admin_user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.SCI_PROPOSAL
        )
        mixer.blend(Instrument, call=self.call)
        self.apps = mixer.cycle(3).blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=self.user,
            call=self.call,
            tac_rank=(x for x in range(3))
        )
        mixer.cycle(3).blend(
            TimeRequest,
            science_application=(app for app in self.apps),
            approved=True
        )

    def test_accept(self):
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'accept', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.ACCEPTED)

    def test_reject(self):
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'reject', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.REJECTED)

    def test_port(self):
        ScienceApplication.objects.update(status=ScienceApplication.ACCEPTED)
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.assertEqual(len(mail.outbox), 3)
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.PORTED)

    def test_email_pi_on_successful_port(self):
        app_id_to_port = self.apps[0].id
        ScienceApplication.objects.filter(pk=app_id_to_port).update(status=ScienceApplication.ACCEPTED)
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual([ScienceApplication.objects.get(pk=app_id_to_port).proposal.pi.email], mail.outbox[0].to)
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).proposal.id, str(mail.outbox[0].message()))
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).call.semester.id, str(mail.outbox[0].message()))

    def test_port_not_accepted(self):
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.assertFalse(Proposal.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.SUBMITTED)

    def test_port_no_approved_requests(self):
        ScienceApplication.objects.update(status=ScienceApplication.ACCEPTED)
        TimeRequest.objects.update(approved=False)
        response = self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.ACCEPTED)
        self.assertContains(response, 'no approved Time Allocations')
        self.assertEqual(len(mail.outbox), 0)

    def test_port_duplicate_tac_rank(self):
        ScienceApplication.objects.update(status=ScienceApplication.ACCEPTED, tac_rank=0)
        response = self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.assertContains(response, 'A proposal named LCO{}-000 already exists.'.format(self.semester))
        # One application out of the bunch was successfully ported, so only one email was sent
        self.assertEqual(len(mail.outbox), 1)
