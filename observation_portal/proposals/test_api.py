from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.urls import reverse
from datetime import datetime
from django.utils import timezone

from observation_portal.proposals.models import Proposal, Membership, Semester, ProposalNotification
from observation_portal.accounts.test_utils import blend_user


class TestProposalApiList(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposals = mixer.cycle(3).blend(Proposal)
        mixer.cycle(3).blend(Membership, user=self.user, proposal=(p for p in self.proposals))

    def test_no_auth(self):
        response = self.client.get(reverse('api:proposals-list'))
        self.assertEqual(response.status_code, 403)

    def test_user_can_view_proposals(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:proposals-list'))
        for p in self.proposals:
            self.assertContains(response, p.id)

    def test_user_cannot_view_other_proposals(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        response = self.client.get(reverse('api:proposals-list'))
        self.assertEqual(response.json()['count'], 0)

    def test_staff_can_view_all_proposals(self):
        admin_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(admin_user)
        response = self.client.get(reverse('api:proposals-list'))
        for p in self.proposals:
            self.assertContains(response, p.id)


class TestProposalApiDetail(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)

    def test_no_auth(self):
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 403)

    def test_user_can_view_proposal(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)

    def test_user_cannot_view_other_proposal(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_can_view_proposal(self):
        admin_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(admin_user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)


class TestNotificationsEnabled(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)

    def test_user_can_enable_notifications(self):
        self.assertEqual(self.user.proposalnotification_set.count(), 0)
        self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(self.user.proposalnotification_set.count(), 1)

    def test_user_can_disable_notifications(self):
        ProposalNotification.objects.create(user=self.user, proposal=self.proposal)
        self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': False},
        )
        self.assertEqual(self.user.proposalnotification_set.count(), 0)

    def test_unauthenticated_user_cannot_do_anything(self):
        self.client.logout()
        response = self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': False},
        )
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_create_notification_on_other_proposal(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        self.assertEqual(other_user.proposalnotification_set.count(), 0)
        response = self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_user.proposalnotification_set.count(), 0)

    def test_staff_user_can_enable_notification_on_any_proposal(self):
        staff_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(staff_user)
        self.assertEqual(staff_user.proposalnotification_set.count(), 0)
        self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(staff_user.proposalnotification_set.count(), 1)

    def test_bad_data(self):
        self.assertEqual(self.user.proposalnotification_set.count(), 0)
        response = self.client.post(
            reverse('api:proposals-proposalnotifications', kwargs={'pk': self.proposal.id}),
            data={'enabled': 'sure'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.proposalnotification_set.count(), 0)


class TestSemesterApi(APITestCase):
    def setUp(self):
        self.semesters = mixer.cycle(3).blend(Semester, start=datetime(2016, 1, 1, tzinfo=timezone.utc),
                                              end=datetime(2016, 2, 1, tzinfo=timezone.utc))

    def test_semester_list(self):
        response = self.client.get(reverse('api:semesters-list'))
        for semester in self.semesters:
            self.assertContains(response, semester.id)

    def test_semester_contains_filter(self):
        later_semester = mixer.blend(Semester, start=datetime(2017, 1, 1, tzinfo=timezone.utc),
                                     end=datetime(2017, 2, 1, tzinfo=timezone.utc))
        response = self.client.get(reverse('api:semesters-list') + '?semester_contains=2017-01-10')
        self.assertContains(response, later_semester.id)
        for semester in self.semesters:
            self.assertNotContains(response, semester.id)

    def test_semester_contains_nonsense_param(self):
        response = self.client.get(reverse('api:semesters-list') + '?semester_contains=icantmakedates')
        for semester in self.semesters:
            self.assertContains(response, semester.id)

    def test_no_semester_contains_filter(self):
        response = self.client.get(reverse('api:semesters-list') + '?semester_contains=2018-01-10')
        self.assertEqual(response.json()['count'], 0)

    def test_semester_detail(self):
        response = self.client.get(reverse('api:semesters-detail', kwargs={'pk': self.semesters[0].id}))
        self.assertContains(response, self.semesters[0].id)
