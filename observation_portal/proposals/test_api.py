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


class TestMembershipLimitApi(APITestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user_1 = blend_user()
        self.ci_user_2 = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI, time_limit=0)
        Membership.objects.create(user=self.ci_user_1, proposal=self.proposal, role=Membership.CI, time_limit=0)
        Membership.objects.create(user=self.ci_user_2, proposal=self.proposal, role=Membership.CI, time_limit=0)

    def test_set_single_limit(self):
        self.client.force_login(self.pi_user)
        membership_1 = self.ci_user_1.membership_set.first()
        membership_2 = self.ci_user_2.membership_set.first()
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 1, 'usernames': [self.ci_user_1.username]},
        )
        membership_1.refresh_from_db()
        membership_2.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(membership_1.time_limit, 3600)
        self.assertEqual(membership_2.time_limit, 0)

    def test_cannot_set_limits_on_other_proposal(self):
        self.client.force_login(self.pi_user)
        other_user = blend_user()
        other_proposal = mixer.blend(Proposal)
        other_membership = Membership.objects.create(user=other_user, proposal=other_proposal, role=Membership.CI)
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': other_proposal.id}),
            data={'time_limit_hours': 300, 'usernames': [other_user.username]},
        )
        other_membership.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_membership.time_limit, -1)

    def test_set_many_limits(self):
        self.client.force_login(self.pi_user)
        ci_users = [blend_user() for _ in range(5)]
        memberships = mixer.cycle(5).blend(
            Membership, user=(c for c in ci_users), proposal=self.proposal, role=Membership.CI
        )
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 2, 'usernames': [ci.username for ci in ci_users]},
        )
        self.assertContains(response, 'Updated 5 CI time limits to 2.0 hours')
        for membership in memberships:
            membership.refresh_from_db()
            self.assertEqual(membership.time_limit, 7200)

    def test_set_bad_time_limit(self):
        self.client.force_login(self.pi_user)
        membership = self.ci_user_1.membership_set.first()
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': '', 'usernames': [self.ci_user_1.username]}
        )
        membership.refresh_from_db()
        self.assertEqual(membership.time_limit, 0)
        self.assertContains(response, 'time_limit_hours', status_code=400)

    def test_set_bad_usernames(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 1, 'usernames': ''},
        )
        self.assertContains(response, 'usernames', status_code=400)

    def test_username_does_not_exist(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 1, 'usernames': ['notauser']},
        )
        self.assertContains(response, 'Updated 0 CI time limits')
        for membership in self.proposal.membership_set.all():
            self.assertEqual(membership.time_limit, 0)

    def test_ci_cannot_set_limit(self):
        self.client.force_login(self.ci_user_1)
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 1000, 'usernames': [self.ci_user_1.username]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.ci_user_1.membership_set.first().time_limit, 0)

    def test_must_be_authenticated_to_set_limits(self):
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 1, 'usernames': [self.ci_user_1.username]},
        )
        self.assertEqual(response.status_code, 403)

    def test_set_no_limit(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-limit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': -1, 'usernames': [self.ci_user_1.username]},
        )
        self.assertContains(response, 'Updated 1 CI time limits')
        self.assertEqual(self.ci_user_1.membership_set.first().time_limit, -3600)
