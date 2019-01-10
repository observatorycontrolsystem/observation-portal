from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
from mixer.backend.django import mixer
from oauth2_provider.models import Application, AccessToken
from unittest.mock import patch

from observation_portal.accounts.models import Profile


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
