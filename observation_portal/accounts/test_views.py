from datetime import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib import auth
from mixer.backend.django import mixer
from django.utils import timezone

from observation_portal.accounts.test_utils import blend_user
from observation_portal.proposals.models import ProposalInvite, Membership, Proposal


class TestIndex(TestCase):
    def setUp(self):
        self.user = blend_user(user_params=dict(
            username='doge',
            email='doge@dog.com'
        ))
        self.user.set_password('sopassword')
        self.user.save()

    def test_no_such_user(self):
        self.client.post(
            reverse('auth_login'),
            {'username': 'imnotreal', 'password': 'wrongpass'},
        )
        user = auth.get_user(self.client)
        self.assertFalse(user.is_authenticated)

    def test_login_fails(self):
        self.client.post(
            reverse('auth_login'),
            {'username': 'doge', 'password': 'wrongpass'},
        )
        user = auth.get_user(self.client)
        self.assertFalse(user.is_authenticated)

    def test_login(self):
        self.client.post(
            reverse('auth_login'),
            {'username': 'doge', 'password': 'sopassword'},
        )
        user = auth.get_user(self.client)
        self.assertTrue(user.is_authenticated)

    def test_login_with_email(self):
        self.client.post(
            reverse('auth_login'),
            {'username': 'doge@dog.com', 'password': 'sopassword'},
        )
        user = auth.get_user(self.client)
        self.assertTrue(user.is_authenticated)

    def test_login_with_email_fails(self):
        self.client.post(
            reverse('auth_login'),
            {'username': 'doge@dog.com', 'password': 'wrongpass'},
        )
        user = auth.get_user(self.client)
        self.assertFalse(user.is_authenticated)


class TestRegistration(TestCase):
    def setUp(self):
        self.reg_data = {
            'first_name': 'Bobby',
            'last_name': 'Shaftoe',
            'institution': 'US Army',
            'title': 'Jarhead',
            'education_user': False,
            'email': 'bshaftoe@army.gov',
            'username': 'bshaftoe',
            'password1': 'imnotcrazy',
            'password2': 'imnotcrazy',
            'tos': True,
        }

    def test_registration(self):
        response = self.client.get(reverse('registration_register'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('registration_register'), self.reg_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'check your email')

        user = User.objects.get(username=self.reg_data['username'])
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.title, self.reg_data['title'])
        self.assertEqual(user.profile.institution, self.reg_data['institution'])

    def test_registration_with_invite(self):
        invitation = mixer.blend(ProposalInvite, email=self.reg_data['email'], membership=None, used=None)
        response = self.client.post(reverse('registration_register'), self.reg_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'check your email')
        invitation = ProposalInvite.objects.get(pk=invitation.id)
        self.assertTrue(invitation.used)
        self.assertTrue(Membership.objects.filter(user__username=self.reg_data['username']).exists())

    def test_registration_with_invite_case_insensitive(self):
        invitation = mixer.blend(ProposalInvite, email=self.reg_data['email'].upper(), membership=None, used=None)
        response = self.client.post(reverse('registration_register'), self.reg_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'check your email')
        invitation = ProposalInvite.objects.get(pk=invitation.id)
        self.assertTrue(invitation.used)
        self.assertTrue(Membership.objects.filter(user__username=self.reg_data['username']).exists())

    def test_registration_with_multiple_invites(self):
        invitations = mixer.cycle(2).blend(ProposalInvite, email=self.reg_data['email'], membership=None, used=None)
        self.client.post(reverse('registration_register'), self.reg_data, follow=True)
        invitation = ProposalInvite.objects.get(pk=invitations[0].id)
        self.assertTrue(invitation.used)
        self.assertTrue(Membership.objects.filter(user__username=self.reg_data['username']).exists())
        invitation = ProposalInvite.objects.get(pk=invitations[1].id)
        self.assertTrue(invitation.used)
        self.assertTrue(Membership.objects.filter(user__username=self.reg_data['username']).exists())

    def test_reqistration_with_multiple_invites_for_same_proposal(self):
        proposal = mixer.blend(Proposal)
        first_invitation = mixer.blend(
            ProposalInvite, email=self.reg_data['email'], proposal=proposal,
            sent=datetime(year=2018, month=10, day=10, tzinfo=timezone.utc), used=None
        )
        second_invitation = mixer.blend(
            ProposalInvite, email=self.reg_data['email'].upper(), proposal=proposal,
            sent=datetime(year=2019, month=10, day=10, tzinfo=timezone.utc), used=None
        )
        self.assertEqual(ProposalInvite.objects.all().count(), 2)
        self.client.post(reverse('registration_register'), self.reg_data, follow=True)
        first_invitation.refresh_from_db()
        second_invitation.refresh_from_db()
        self.assertFalse(first_invitation.used)
        self.assertTrue(second_invitation.used)
        self.assertTrue(Membership.objects.filter(user__username=self.reg_data['username']).exists())

    def test_education_register(self):
        reg_data = self.reg_data.copy()
        reg_data['education_user'] = True
        response = self.client.post(reverse('registration_register'), reg_data, follow=True)
        self.assertContains(response, 'check your email')

        user = User.objects.get(username=reg_data['username'])
        self.assertTrue(user.profile.education_user)
        self.assertTrue(user.profile.notifications_enabled)
        self.assertTrue(user.profile.notifications_on_authored_only)
        self.assertTrue(user.profile.view_authored_requests_only)

    def test_username_max_length(self):
        reg_data = self.reg_data.copy()
        reg_data['username'] = 'x' * 55
        response = self.client.post(reverse('registration_register'), reg_data, follow=True)
        self.assertContains(response, 'at most 50 characters')
        self.assertFalse(User.objects.count())
