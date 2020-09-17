from datetime import timedelta

from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.urls import reverse
from django.utils import timezone

from observation_portal.sciapplications.models import Call


class TestCallAPI(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        now = timezone.now()
        self.open_call = mixer.blend(
            Call, proposal_type=Call.SCI_PROPOSAL, opens=now - timedelta(days=1), deadline=now + timedelta(days=1)
        )
        self.closed_call = mixer.blend(
            Call, proposal_type=Call.SCI_PROPOSAL, opens=now - timedelta(days=2), deadline=now - timedelta(days=1)
        )

    def test_get_calls(self):
        response = self.client.get(reverse('api:calls-list'))
        self.assertEqual(len(response.json()['results']), 1)
        self.assertContains(response, self.open_call.id)
