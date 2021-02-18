from django.core import mail
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from mixer.backend.django import mixer
from django_dramatiq.test import DramatiqTestCase

from observation_portal.proposals.models import Semester, Proposal
from observation_portal.sciapplications.models import ScienceApplication, Call, Instrument, TimeRequest


def order_mail_invite_then_approval(mailbox):
    ordered_mailbox = []
    # First look for any proposal invite emails and add them
    for item in mailbox:
        if 'You have been added' in item.subject:
            ordered_mailbox.append(item)
    # Then look for an proposal approval emails and add them
    for item in mailbox:
        if 'has been approved' in item.subject:
            ordered_mailbox.append(item)

    return ordered_mailbox


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
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 3)
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.PORTED)

    def test_email_pi_on_successful_port_pi_is_submitter(self):
        app_id_to_port = self.apps[0].id
        ScienceApplication.objects.filter(pk=app_id_to_port).update(status=ScienceApplication.ACCEPTED)
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ScienceApplication.objects.get(pk=app_id_to_port).proposal.pi.email, self.user.email)
        self.assertEqual([ScienceApplication.objects.get(pk=app_id_to_port).proposal.pi.email], mail.outbox[0].to)
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).proposal.id, str(mail.outbox[0].message()))
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).call.semester.id, str(mail.outbox[0].message()))

    def test_email_pi_on_successful_port_when_registered_pi_is_not_submitter(self):
        other_user = mixer.blend(User)
        app_id_to_port = self.apps[0].id
        ScienceApplication.objects.filter(pk=app_id_to_port).update(status=ScienceApplication.ACCEPTED)
        ScienceApplication.objects.filter(pk=app_id_to_port).update(pi=other_user.email)
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
        # If the PI is registered but is not the submitter, they will receive two emails- one telling them
        # their proposal has been approved, and another telling them them that they have been added to that proposal
        # and can begin submitting requests. The approval email is second.
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(ScienceApplication.objects.get(pk=app_id_to_port).proposal.pi.email, other_user.email)
        ordered_mailbox = order_mail_invite_then_approval(mail.outbox)
        # Added to proposal email
        self.assertEqual([other_user.email], ordered_mailbox[0].to)
        self.assertIn('You have been added to', str(ordered_mailbox[0].message()))
        # Proposal approved email
        self.assertEqual([other_user.email], ordered_mailbox[1].to)
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).proposal.id, str(ordered_mailbox[1].message()))
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).call.semester.id, str(ordered_mailbox[1].message()))

    def test_email_pi_on_successful_port_when_pi_is_not_registered(self):
        non_registered_email = 'somenonexistantuser@email.com'
        app_id_to_port = self.apps[0].id
        ScienceApplication.objects.filter(pk=app_id_to_port).update(status=ScienceApplication.ACCEPTED)
        ScienceApplication.objects.filter(pk=app_id_to_port).update(pi=non_registered_email)
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
        # If the PI is not registered, then 2 emails will be sent out- one inviting them to register an account, and
        # one letting them know their proposal has been approved. The accepted email is sent second.
        self.assertEqual(len(mail.outbox), 2)
        ordered_mailbox = order_mail_invite_then_approval(mail.outbox)
        # Proposal invitation email
        self.assertEqual([non_registered_email], ordered_mailbox[0].to)
        self.assertIn('Please use the following link to register your account', str(ordered_mailbox[0].message()))
        # Proposal approved email
        self.assertEqual([non_registered_email], ordered_mailbox[1].to)
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).proposal.id, str(ordered_mailbox[1].message()))
        self.assertIn(ScienceApplication.objects.get(pk=app_id_to_port).call.semester.id, str(ordered_mailbox[1].message()))

    def test_port_not_accepted(self):
        self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
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
        self.broker.join('default')
        self.worker.join()
        for app in self.apps:
            self.assertEqual(ScienceApplication.objects.get(pk=app.id).status, ScienceApplication.ACCEPTED)
        self.assertContains(response, 'no approved Time Allocations')
        self.assertEqual(len(mail.outbox), 0)

    def test_port_duplicate_time_requests(self):
        semester = mixer.blend(Semester)
        instrument = mixer.blend(Instrument)
        # Prepare the sciapp for porting
        sciapp = ScienceApplication.objects.first()
        sciapp.status = ScienceApplication.ACCEPTED
        sciapp.tac_rank = 0
        sciapp.save()
        # Create duplicate time requests for the sciapp
        mixer.blend(TimeRequest, science_application=sciapp, instrument=instrument, semester=semester, approved=True)
        mixer.blend(TimeRequest, science_application=sciapp, instrument=instrument, semester=semester, approved=True)
        response = self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(sciapp.pk)]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
        sciapp.refresh_from_db()
        self.assertEqual(sciapp.status, ScienceApplication.ACCEPTED)
        self.assertContains(response, 'has more than one approved time request')
        # The application was not ported, so no email was sent
        self.assertEqual(len(mail.outbox), 0)

    def test_port_duplicate_tac_rank(self):
        ScienceApplication.objects.update(status=ScienceApplication.ACCEPTED, tac_rank=0)
        response = self.client.post(
            reverse('admin:sciapplications_scienceapplication_changelist'),
            data={'action': 'port', '_selected_action': [str(app.pk) for app in self.apps]},
            follow=True
        )
        self.broker.join('default')
        self.worker.join()
        self.assertContains(response, 'A proposal named LCO{}-000 already exists.'.format(self.semester))
        # One application out of the bunch was successfully ported, so only one email was sent
        self.assertEqual(len(mail.outbox), 1)
