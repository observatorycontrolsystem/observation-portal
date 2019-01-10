from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.contrib import auth
from mixer.backend.django import mixer
from django.core import mail

from observation_portal.common.test_helpers import ConfigDBTestMixin
from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import ProposalInvite, Membership, Proposal, TimeAllocation


class TestIndex(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='doge',
            password='sopassword',
            email='doge@dog.com'
        )

    def test_index_page(self):
        response = self.client.get(reverse('requestgroups:list'))
        self.assertContains(response, 'Observation Portal')

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


class TestProfile(ConfigDBTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.profile = mixer.blend(Profile, notifications_enabled=True)
        self.data = {
            'first_name': self.profile.user.first_name,
            'last_name': self.profile.user.last_name,
            'email': self.profile.user.email,
            'username': self.profile.user.username,
            'institution': self.profile.institution,
            'title': self.profile.title,
            'notifications_enabled': self.profile.notifications_enabled
        }
        self.client.force_login(self.profile.user)

    def test_update(self):
        good_data = self.data.copy()
        good_data['email'] = 'hi@lco.global'
        response = self.client.post(reverse('profile'), good_data, follow=True)
        self.assertContains(response, 'Profile successfully updated')
        self.assertEqual(Profile.objects.get(pk=self.profile.id).user.email, 'hi@lco.global')

    def test_cannot_set_staff_view(self):
        good_data = self.data.copy()
        good_data['staff_view'] = True
        response = self.client.post(reverse('profile'), good_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.staff_view)

    def test_staff_can_enable_staff_view(self):
        self.profile.user.is_staff = True
        self.profile.user.save()
        good_data = self.data.copy()
        good_data['staff_view'] = True
        response = self.client.post(reverse('profile'), good_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.staff_view)

    def test_unique_email(self):
        mixer.blend(User, email='first@example.com')
        bad_data = self.data.copy()
        bad_data['email'] = 'first@example.com'
        response = self.client.post(reverse('profile'), bad_data, follow=True)
        self.assertContains(response, 'User with this email already exists')
        self.assertNotEqual(Profile.objects.get(pk=self.profile.id).user.email, 'first@example.com')

    def test_required(self):
        bad_data = self.data.copy()
        del bad_data['username']
        response = self.client.post(reverse('profile'), bad_data, follow=True)
        self.assertContains(response, 'This field is required')
        self.assertTrue(Profile.objects.get(pk=self.profile.id).user.username)

    def test_api_call(self):
        response = self.client.get(reverse('api:profile'))
        self.assertEqual(response.json()['username'], self.profile.user.username)

    def test_avaialable_instruments(self):
        response = self.client.get(reverse('api:profile'))
        self.assertFalse(response.json()['available_instrument_types'])

        proposal = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, proposal=proposal, user=self.profile.user)
        mixer.blend(TimeAllocation, proposal=proposal, telescope_class="1m0")

        response = self.client.get(reverse('api:profile'))
        self.assertGreater(len(response.json()['available_instrument_types']), 0)


class TestToken(TestCase):
    def setUp(self):
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)

    def test_user_gets_api_token(self):
        with self.assertRaises(Token.DoesNotExist):
            Token.objects.get(user=self.user)
        self.client.get(reverse('profile'))
        self.assertTrue(Token.objects.get(user=self.user))

    def test_user_can_revoke_token(self):
        token_key = self.user.profile.api_token.key
        self.client.post(reverse('revoke-api-token'))
        self.assertNotEqual(token_key, self.user.profile.api_token.key)


class TestAccountRemovalRequest(TestCase):
    def setUp(self):
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)

    def test_request_sends_email(self):
        form_data = {'reason': 'Because I hate Astronomy'}
        response = self.client.post(reverse('account-removal'), form_data, follow=True)
        self.assertContains(response, 'Account removal request successfully submitted')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(form_data['reason'], str(mail.outbox[0].message()))
