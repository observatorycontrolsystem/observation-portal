from django.test import TestCase
from mixer.backend.django import mixer
from django.urls import reverse

from observation_portal.proposals.models import Proposal, Membership
from observation_portal.observations.models import Observation
from observation_portal.common.test_helpers import create_simple_requestgroup
from observation_portal.accounts.test_utils import blend_user


class TestObservationsDetailView(TestCase):
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.rg = create_simple_requestgroup(self.user, self.proposal)
        self.observation = mixer.blend(Observation, request=self.rg.requests.first())

        self.staff_user = blend_user(user_params={'is_staff': True, 'is_superuser': True}, profile_params={'staff_view': True})
        self.staff_proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.staff_proposal, user=self.staff_user)
        self.staff_rg = create_simple_requestgroup(self.staff_user, self.staff_proposal)
        self.staff_observation = mixer.blend(Observation, request=self.staff_rg.requests.first())

        self.public_proposal = mixer.blend(Proposal, public=True)
        mixer.blend(Membership, proposal=self.public_proposal, user=self.user)
        self.public_requestgroup = create_simple_requestgroup(self.user, self.public_proposal)
        self.public_observation = mixer.blend(Observation, request=self.public_requestgroup.requests.first())

    def test_unauthenticated_user_sees_only_public_observation(self):
        public_response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.public_observation.id}))
        self.assertEqual(public_response.status_code, 200)
        non_public_response = self.client.get(reverse('observations:observation-detail', args=[self.observation.id]))
        self.assertEqual(non_public_response.status_code, 404)

    def test_authenticated_user_sees_their_observation_but_not_others(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 200)
        staff_response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.staff_observation.id}))
        self.assertEqual(staff_response.status_code, 404)

    def test_staff_user_with_staff_view_sees_others_observation(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 200)

    def test_staff_user_without_staff_view_doesnt_see_others_observation(self):
        self.staff_user.profile.staff_view = False
        self.staff_user.profile.save()
        response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 404)

    def test_user_authored_only_enabled(self):
        user = blend_user(profile_params={'view_authored_requests_only': True})
        mixer.blend(Membership, proposal=self.public_proposal, user=user)
        requestgroup = create_simple_requestgroup(user, self.public_proposal)
        observation = mixer.blend(Observation, request=requestgroup.requests.first())
        self.client.force_login(user)
        response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': self.public_observation.id}))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('observations:observation-detail', kwargs={'pk': observation.id}))
        self.assertEqual(response.status_code, 200)


class TestObservationsListView(TestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.requestgroups = [create_simple_requestgroup(self.user, self.proposal) for _ in range(3)]
        self.observations = mixer.cycle(3).blend(
            Observation,
            request=(rg.requests.first() for rg in self.requestgroups),
            state='PENDING'
        )
        self.public_proposal = mixer.blend(Proposal, public=True)
        mixer.blend(Membership, proposal=self.public_proposal, user=self.user)
        self.public_requestgroups = [create_simple_requestgroup(self.user, self.public_proposal) for _ in range(3)]
        self.public_observations = mixer.cycle(3).blend(
            Observation,
            request=(rg.requests.first() for rg in self.public_requestgroups),
            state='PENDING'
        )
        self.other_user = blend_user()
        self.other_proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.other_proposal, user=self.other_user)
        self.other_requestgroups = [create_simple_requestgroup(self.other_user, self.other_proposal) for _ in range(3)]
        self.other_observations = mixer.cycle(3).blend(
            Observation,
            request=(rg.requests.first() for rg in self.other_requestgroups),
            state='PENDING'
        )

    def test_unauthenticated_user_only_sees_public_observations(self):
        response = self.client.get(reverse('observations:observation-list'))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.proposal.id, str(response.content))
        self.assertNotIn(self.other_proposal.id, str(response.content))

    def test_authenticated_user_sees_their_observations(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('observations:observation-list'))
        self.assertIn(self.proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.other_proposal.id, str(response.content))

    def test_staff_user_with_staff_view_sees_everything(self):
        staff_user = blend_user(user_params={'is_staff': True, 'is_superuser': True}, profile_params={'staff_view': True})
        self.client.force_login(staff_user)
        response = self.client.get(reverse('observations:observation-list'))
        self.assertIn(self.proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertIn(self.other_proposal.id, str(response.content))

    def test_staff_user_without_staff_view_sees_only_their_observations(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse('observations:observation-list'))
        self.assertIn(self.proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.other_proposal.id, str(response.content))

    def test_user_with_authored_only(self):
        user = blend_user(profile_params={'view_authored_requests_only': True})
        mixer.blend(Membership, proposal=self.proposal, user=user)
        response = self.client.get(reverse('observations:observation-list'))
        self.assertNotIn(self.proposal.id, str(response.content))
