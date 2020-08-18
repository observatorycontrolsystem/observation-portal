from datetime import timedelta
from unittest.mock import patch
import copy

from django.test import TestCase
from rest_framework.test import APITestCase
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from mixer.backend.django import mixer
from oauth2_provider.models import Application, AccessToken
from rest_framework.authtoken.models import Token
from django.core import mail
from django_dramatiq.test import DramatiqTestCase

from observation_portal.accounts.test_utils import blend_user
from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import Proposal, Membership, TimeAllocation


class TestArchiveBearerToken(TestCase):
    def setUp(self):
        self.profile = mixer.blend(Profile)

    def test_no_archive_app(self):
        self.assertEqual(self.profile.archive_bearer_token, '')

    def test_new_token(self):
        mixer.blend(Application, name='Archive')
        self.assertTrue(self.profile.archive_bearer_token)

    def test_existing_token(self):
        app = mixer.blend(Application, name='Archive')
        at = mixer.blend(
            AccessToken,
            application=app,
            user=self.profile.user,
            expires=timezone.now() + timedelta(days=30)
        )
        self.assertEqual(self.profile.archive_bearer_token, at.token)

    def test_expired_token(self):
        app = mixer.blend(Application, name='Archive')
        at = mixer.blend(
            AccessToken,
            application=app,
            user=self.profile.user,
            expires=timezone.now() - timedelta(days=1)
        )
        self.assertNotEqual(self.profile.archive_bearer_token, at.token)


class TestAPIQuota(TestCase):
    def setUp(self):
        user = mixer.blend(User)
        self.profile = mixer.blend(Profile, user=user)

    def test_quota_is_zero(self):
        self.assertEqual(self.profile.api_quota['used'], 0)

    @patch('django.core.cache.cache.get', return_value=([1504903107.1322677, 1504903106.6130717]))
    def test_quota_used(self, cache_mock):
        self.assertEqual(self.profile.api_quota['used'], 2)


class TestInitCredentialsCommand(TestCase):
    def test_credentials_are_setup(self):
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Proposal.objects.count(), 0)
        call_command('init_e2e_credentials', '-pMyProposal', '-umy_user', '-tmy_token')

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.all()[0]
        self.assertEqual(user.username, 'my_user')

        self.assertEqual(Proposal.objects.count(), 1)
        proposal = Proposal.objects.all()[0]
        self.assertEqual(proposal.id, 'MyProposal')

        token = Token.objects.get(user=user)
        self.assertEqual(token.key, 'my_token')


class TestRevokeTokenAPI(APITestCase):
    def setUp(self) -> None:
        super(TestRevokeTokenAPI, self).setUp()
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_revoke_token(self):
        initial_token = self.user.profile.api_token.key
        response = self.client.post(reverse('api:revoke_api_token'))
        self.assertContains(response, 'API token revoked', status_code=200)
        self.user.refresh_from_db()
        self.assertNotEqual(initial_token, self.user.profile.api_token.key)

    def test_unauthenticated(self):
        self.client.logout()
        initial_token = self.user.profile.api_token.key
        response = self.client.post(reverse('api:revoke_api_token'))
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(initial_token, self.user.profile.api_token.key)


class TestAccountRemovalApiRequest(DramatiqTestCase):
    def setUp(self):
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_send_removal_request(self):
        reason = 'I no longer enjoy astronomy.'
        response = self.client.post(reverse('api:account_removal_request'), data={'reason': reason})
        self.assertContains(response, 'Account removal request successfully submitted')
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reason, str(mail.outbox[0].message()))

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.post(reverse('api:account_removal_request'))
        self.assertEqual(response.status_code, 403)

    def test_empty_reason_supplied(self):
        response = self.client.post(reverse('api:account_removal_request'), data={'reason': ''})
        self.assertEqual(response.status_code, 400)

    def test_no_reason_supplied(self):
        response = self.client.post(reverse('api:account_removal_request'), data={})
        self.assertEqual(response.status_code, 400)


class TestAcceptTermsAPI(APITestCase):
    def setUp(self) -> None:
        super(TestAcceptTermsAPI, self).setUp()
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_accept_terms(self):
        original_terms_accepted = timezone.now() - timedelta(days=1)
        self.user.profile.terms_accepted = original_terms_accepted
        self.user.profile.save()
        response = self.client.post(reverse('api:accept_terms'))
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertGreater(self.user.profile.terms_accepted, original_terms_accepted)

    def test_accept_terms_unauthenticated(self):
        self.client.logout()
        response = self.client.post(reverse('api:accept_terms'))
        self.assertEqual(response.status_code, 403)

    def test_accept_terms_user_with_no_profile(self):
        user = mixer.blend(User)
        with self.assertRaises(Profile.DoesNotExist):
            _ = user.profile
        response = self.client.post(reverse('api:accept_terms'))
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(self.user.profile.terms_accepted)


class TestProfileAPI(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = blend_user(profile_params={'notifications_enabled': True})
        self.profile = self.user.profile
        self.data = {
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'email': self.user.email,
            'username': self.user.username,
            'profile': {
                'institution': self.user.profile.institution,
                'title': self.user.profile.title,
                'notifications_enabled': self.user.profile.notifications_enabled,
            }
        }
        self.client.force_login(self.user)

    def test_get(self):
        response = self.client.get(reverse('api:profile'))
        self.assertEqual(response.json()['username'], self.user.username)

    def test_unauthenticated_get(self):
        self.client.logout()
        response = self.client.get(reverse('api:profile'))
        self.assertEqual(response.status_code, 403)

    def test_update(self):
        good_data = copy.deepcopy(self.data)
        good_data['email'] = 'hi@lco.global'
        response = self.client.patch(reverse('api:profile'), good_data)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'hi@lco.global')

    def test_unauthenticated_update(self):
        self.client.logout()
        good_data = copy.deepcopy(self.data)
        original_email = good_data['email']
        good_data['email'] = 'hi@lco.global'
        response = self.client.patch(reverse('api:profile'), data=good_data)
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)

    def test_cannot_set_staff_view(self):
        good_data = copy.deepcopy(self.data)
        good_data['profile']['staff_view'] = True
        response = self.client.patch(reverse('api:profile'), data=good_data)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile.staff_view)

    def test_cannot_set_is_staff(self):
        good_data = copy.deepcopy(self.data)
        good_data['is_staff'] = True
        self.client.patch(reverse('api:profile'), data=good_data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_staff_can_enable_staff_view(self):
        self.user.is_staff = True
        self.user.save()
        good_data = copy.deepcopy(self.data)
        good_data['profile']['staff_view'] = True
        response = self.client.patch(reverse('api:profile'), data=good_data)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile.staff_view)

    def test_unique_email(self):
        duplicate_email = 'first@example.com'
        mixer.blend(User, email=duplicate_email)
        bad_data = copy.deepcopy(self.data)
        bad_data['email'] = duplicate_email
        response = self.client.patch(reverse('api:profile'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('User with this email already exists', response.json()['email'][0])
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, duplicate_email)

    def test_available_instruments(self):
        response = self.client.get(reverse('api:profile'))
        self.assertFalse(response.json()['available_instrument_types'])

        proposal = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, proposal=proposal, user=self.profile.user)
        mixer.blend(TimeAllocation, proposal=proposal, telescope_class='1m0')

        response = self.client.get(reverse('api:profile'))
        self.assertGreater(len(response.json()['available_instrument_types']), 0)

    def test_proposals(self):
        response = self.client.get(reverse('api:profile'))
        self.assertEqual(len(response.json()['proposals']), 0)

        proposal = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, proposal=proposal, user=self.user)
        response = self.client.get(reverse('api:profile'))

        self.assertEqual(len(response.json()['proposals']), 1)
        self.assertEqual(response.json()['proposals'][0]['id'], proposal.id)

    def test_user_gets_api_token(self):
        with self.assertRaises(Token.DoesNotExist):
            Token.objects.get(user=self.user)
        self.client.get(reverse('api:profile'))
        self.assertTrue(Token.objects.get(user=self.user))
