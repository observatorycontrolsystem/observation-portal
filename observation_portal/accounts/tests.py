from datetime import timedelta
from unittest.mock import patch, ANY, call
import copy
import responses

from django.test import TestCase
from rest_framework.test import APITestCase
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from mixer.backend.django import mixer
from rest_framework.authtoken.models import Token
from django.core import mail
from django_dramatiq.test import DramatiqTestCase
from rest_framework import status

from observation_portal.accounts.test_utils import blend_user
from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import Proposal, Membership, TimeAllocation


class TestAPIQuota(TestCase):
    def setUp(self):
        user = blend_user()
        self.profile = user.profile

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
        good_data['email'] = 'hi@example.com'
        response = self.client.patch(reverse('api:profile'), good_data)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'hi@example.com')

    def test_unauthenticated_update(self):
        self.client.logout()
        good_data = copy.deepcopy(self.data)
        original_email = good_data['email']
        good_data['email'] = 'hi@example.com'
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
        blend_user(user_params={'email': duplicate_email})
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
        mixer.blend(TimeAllocation, proposal=proposal, instrument_types=['1M0-SCICAM-SBIG'])

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


class TestClientUserUpdates(DramatiqTestCase):
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.api_token = self.user.profile.api_token.key  # This triggers creating the api_token if it doesn't exist
        self.profile = self.user.profile
        self.client.force_login(self.user)

    def test_user_update_triggers_client_user_update(self):
        with self.settings(OAUTH_CLIENT_APPS_BASE_URLS=['http://test1.lco.global', 'http://test2.lco.global']):
            responses.add(responses.POST, 'http://test1.lco.global/authprofile/addupdateuser/',
                    json={'message': 'User account updated'}, status=200)

            responses.add(responses.POST, 'http://test2.lco.global/authprofile/addupdateuser/',
                    json={'message': 'User account updated'}, status=200)

            self.user.is_staff = not self.user.is_staff
            self.user.save()

            self.broker.join('default')
            self.worker.join()

            self.assertGreaterEqual(len(responses.calls), 2)
            self.assertEqual(responses.calls[-2].request.url, 'http://test1.lco.global/authprofile/addupdateuser/')
            self.assertEqual(responses.calls[-2].response.text, '{"message": "User account updated"}')
            self.assertEqual(responses.calls[-1].request.url, 'http://test2.lco.global/authprofile/addupdateuser/')
            self.assertEqual(responses.calls[-1].response.text, '{"message": "User account updated"}')

    def test_profile_update_triggers_client_user_update(self):
        with self.settings(OAUTH_CLIENT_APPS_BASE_URLS=['http://test1.lco.global', 'http://test2.lco.global']):
            responses.add(responses.POST, 'http://test1.lco.global/authprofile/addupdateuser/',
                    json={'message': 'User account updated'}, status=200)

            responses.add(responses.POST, 'http://test2.lco.global/authprofile/addupdateuser/',
                    json={'message': 'User account updated'}, status=200)

            self.profile.staff_view = not self.profile.staff_view
            self.profile.save()

            self.broker.join('default')
            self.worker.join()

            self.assertGreaterEqual(len(responses.calls), 2)
            self.assertEqual(responses.calls[-2].request.url, 'http://test1.lco.global/authprofile/addupdateuser/')
            self.assertEqual(responses.calls[-2].response.text, '{"message": "User account updated"}')
            self.assertEqual(responses.calls[-1].request.url, 'http://test2.lco.global/authprofile/addupdateuser/')
            self.assertEqual(responses.calls[-1].response.text, '{"message": "User account updated"}')

    def test_revoking_token_triggers_client_user_update(self):
        with self.settings(OAUTH_CLIENT_APPS_BASE_URLS=['http://test1.lco.global']):
            responses.add(responses.POST, 'http://test1.lco.global/authprofile/addupdateuser/',
                    json={'message': 'User account updated'}, status=200)

            response = self.client.post(reverse('api:revoke_api_token'))
            self.assertContains(response, 'API token revoked', status_code=200)

            self.broker.join('default')
            self.worker.join()

            self.assertGreaterEqual(len(responses.calls), 1)
            self.assertEqual(responses.calls[-1].request.url, 'http://test1.lco.global/authprofile/addupdateuser/')
            self.assertEqual(responses.calls[-1].response.text, '{"message": "User account updated"}')


class TestBulkCreateUsersApi(APITestCase):

    def setUp(self):
        super().setUp()

        send_mail_patcher = patch("observation_portal.accounts.serializers.send_mail")
        self.addCleanup(send_mail_patcher.stop)
        self.send_mail_mock = send_mail_patcher.start()

        make_rand_pass_patcher = patch("observation_portal.accounts.serializers.User.objects.make_random_password")
        self.addCleanup(make_rand_pass_patcher.stop)
        self.make_rand_pass_mock = make_rand_pass_patcher.start()
        self.make_rand_pass_mock.return_value = "mockpass"

        self.staff_user = blend_user(
            user_params={
                "username": "staff",
                "is_staff": True,
            }
        )
        self.existing_user = blend_user(
            user_params={
                "username": "existing",
                "email": "existing@domain.example",
                "is_staff": False,
            }
        )

        self.client.force_authenticate(self.staff_user)

    def test_duplicate_usernames_error(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "same",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
                {
                    "username": "same",
                    "email": "user2@domain.example",
                    "first_name": "user2",
                    "last_name": "user2",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data,
            {"users": ["username 'same' provided multiple times"]}
        )

    def test_duplicate_emails_error(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "same@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
                {
                    "username": "user2",
                    "email": "same@domain.example",
                    "first_name": "user2",
                    "last_name": "user2",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data,
            {"users": ["email 'same@domain.example' provided multiple times"]}
        )

    def test_exisiting_username_error(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "existing",
                    "email": "new@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data,
            {"users": {0: {"username": ["username already exists"]}}}
        )

    def test_existing_email_error(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "new_username",
                    "email": "existing@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data,
            {"users": {0: {"email": ["user with email already exists"]}}}
        )

    def test_existing_username_and_email_error(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "existing",
                    "email": "existing@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data,
            {"users": {0: {
                "email": ["user with email already exists"],
                "username": ["username already exists"],
            }}}
        )

    def test_default(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            resp.data,
            {"users": [{
                "username": "user1",
                "email": "user1@domain.example",
                "first_name": "user1",
                "last_name": "user1",
                "institution": "na",
                "title": "na",
                "education_user": True,
            }]}
        )
        self.make_rand_pass_mock.assert_called_once_with(length=12, allowed_chars=ANY)
        self.assertEqual(
            self.staff_user,
            User.objects.get(username="user1").profile.created_by
        )
        self.assertEqual(self.staff_user.created_profiles.count(), 1)
        self.assertEqual(
            self.staff_user.created_profiles.first().user,
            User.objects.get(username="user1")
        )

    def test_override_default(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "password": "inputpass",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na",
                    "education_user": False,
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            resp.data,
            {"users": [{
                "username": "user1",
                "email": "user1@domain.example",
                "first_name": "user1",
                "last_name": "user1",
                "institution": "na",
                "title": "na",
                "education_user": False,
            }]}
        )
        self.make_rand_pass_mock.assert_not_called()
        self.send_mail_mock.send.assert_called_once_with(ANY, ANY, ANY, ["user1@domain.example"])

    def test_many(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
                {
                    "username": "user2",
                    "email": "user2@domain.example",
                    "first_name": "user2",
                    "last_name": "user2",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            resp.data,
            {"users": [
                {
                  "username": "user1",
                  "email": "user1@domain.example",
                  "first_name": "user1",
                  "last_name": "user1",
                  "institution": "na",
                  "title": "na",
                  "education_user": True,
                },
                {
                  "username": "user2",
                  "email": "user2@domain.example",
                  "first_name": "user2",
                  "last_name": "user2",
                  "institution": "na",
                  "title": "na",
                  "education_user": True,
                }
            ]}
        )
        self.assertEqual(
            self.send_mail_mock.send.call_args_list,
            [call(ANY, ANY, ANY, ["user1@domain.example"]), call(ANY, ANY, ANY, ["user2@domain.example"])]
        )

        self.assertEqual(self.staff_user.created_profiles.count(), 2)
        for u in ["user1", "user2"]:
            self.assertEqual(
                self.staff_user,
                User.objects.get(username=u).profile.created_by
            )
            self.assertEqual(
                self.staff_user.created_profiles.get(user__username=u).user,
                User.objects.get(username=u)
            )

    def test_as_non_auth(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        self.client.force_authenticate(user=None)
        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_as_non_staff(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }

        self.client.force_authenticate(user=self.existing_user)
        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_as_PI(self):
        url = reverse("api:users-bulk")
        data = {
            "users": [
                {
                    "username": "user1",
                    "email": "user1@domain.example",
                    "first_name": "user1",
                    "last_name": "user1",
                    "institution": "na",
                    "title": "na"
                },
            ]
        }
        proposal = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, role=Membership.PI, proposal=proposal, user=self.existing_user)

        self.client.force_authenticate(user=self.existing_user)

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_accept_pending_proposal_invites_on_account_creation(self):
        # as a PI
        proposal1 = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, role=Membership.PI, proposal=proposal1, user=self.existing_user)

        proposal2 = mixer.blend(Proposal, active=True)
        mixer.blend(Membership, role=Membership.PI, proposal=proposal2, user=self.existing_user)

        self.client.force_authenticate(user=self.existing_user)

        # create proposal invites for users
        resp = self.client.post(
            reverse("api:proposals-invite", args=[proposal1.pk]),
            {
                "emails": ["user1@domain.example", "user2@domain.example"]
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(
            reverse("api:proposals-invite", args=[proposal2.pk]),
            {
                "emails": ["user1@domain.example", "user3@domain.example"]
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # they should be in pending state
        resp = self.client.get(
            f"{reverse('api:invitations-list')}?pending=true&proposal={proposal1.pk}"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 2)

        resp = self.client.get(
            f"{reverse('api:invitations-list')}?pending=true&proposal={proposal2.pk}"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 2)

        # create users
        resp = self.client.post(
            reverse("api:users-bulk"),
            data = {
                "users": [
                    {
                        "username": "user1",
                        "email": "user1@domain.example",
                        "first_name": "user1",
                        "last_name": "user1",
                        "institution": "na",
                        "title": "na"
                    },
                    {
                        "username": "user2",
                        "email": "user2@domain.example",
                        "first_name": "user2",
                        "last_name": "user2",
                        "institution": "na",
                        "title": "na"
                    },
                ]
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # there should be no pending for created users
        resp = self.client.get(
            f"{reverse('api:invitations-list')}?pending=true&proposal={proposal1.pk}"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 0)

        resp = self.client.get(
            f"{reverse('api:invitations-list')}?pending=true&proposal={proposal2.pk}"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["email"], "user3@domain.example")
