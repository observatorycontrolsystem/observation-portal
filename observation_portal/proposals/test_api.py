from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.urls import reverse
from datetime import datetime, timedelta
from django.utils import timezone

from observation_portal.proposals.models import (
    Proposal, Membership, Semester, ProposalNotification, ProposalInvite, TimeAllocation
)
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

    def test_staff_can_view_own_proposals(self):
        admin_user = blend_user(user_params={'is_staff': True})
        proposals = mixer.cycle(3).blend(Proposal)
        mixer.cycle(3).blend(Membership, user=admin_user, proposal=(p for p in proposals))
        self.client.force_login(admin_user)
        response = self.client.get(reverse('api:proposals-list'))
        self.assertEqual(response.json()['count'], 3)
        for p in proposals:
            self.assertContains(response, p.id)

    def test_staff_with_staff_view_set_can_view_all_proposals(self):
        admin_user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
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
        self.assertFalse('users' in response.json())
        self.assertFalse('notes' in response.json())
        self.assertTrue('pis' in response.json())

    def test_user_cannot_view_other_proposal(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_view_proposal(self):
        admin_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(admin_user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_with_staff_view_set_can_view_proposal(self):
        admin_user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(admin_user)
        response = self.client.get(reverse('api:proposals-detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)


class TestUpdateProposalNotificationsApi(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)

    def test_user_can_enable_notifications(self):
        self.assertEqual(self.user.proposalnotification_set.count(), 0)
        self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(self.user.proposalnotification_set.count(), 1)

    def test_user_can_disable_notifications(self):
        ProposalNotification.objects.create(user=self.user, proposal=self.proposal)
        self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': False},
        )
        self.assertEqual(self.user.proposalnotification_set.count(), 0)

    def test_unauthenticated_user_cannot_do_anything(self):
        self.client.logout()
        response = self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': False},
        )
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_create_notification_on_other_proposal(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        self.assertEqual(other_user.proposalnotification_set.count(), 0)
        response = self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_user.proposalnotification_set.count(), 0)

    def test_staff_user_with_staff_view_set_can_enable_notification_on_any_proposal(self):
        staff_user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(staff_user)
        self.assertEqual(staff_user.proposalnotification_set.count(), 0)
        self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': True},
        )
        self.assertEqual(staff_user.proposalnotification_set.count(), 1)

    def test_bad_data(self):
        self.assertEqual(self.user.proposalnotification_set.count(), 0)
        response = self.client.post(
            reverse('api:proposals-notification', kwargs={'pk': self.proposal.id}),
            data={'enabled': 'sure'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.proposalnotification_set.count(), 0)


class TestSemesterApi(APITestCase):
    def setUp(self):
        self.semesters = mixer.cycle(3).blend(Semester, start=datetime(2016, 1, 1, tzinfo=timezone.utc),
                                              end=datetime(2016, 2, 1, tzinfo=timezone.utc))
        self.proposal = mixer.blend(Proposal, active=True, non_science=False)
        mixer.blend(Membership, proposal=self.proposal, user=blend_user(), role=Membership.PI)
        mixer.blend(TimeAllocation, semester=self.semesters[0], proposal=self.proposal)

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

    def test_staff_can_get_semester_timallocations(self):
        self.client.force_login(blend_user(user_params={'is_staff': True}))
        response = self.client.get(reverse('api:semesters-timeallocations', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['proposal']['id'], self.proposal.id)

    def test_unauthenticated_user_cannot_get_semester_timeallocations(self):
        response = self.client.get(reverse('api:semesters-timeallocations', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 403)

    def test_non_staff_user_cannot_get_semester_timeallocations(self):
        self.client.force_login(blend_user())
        response = self.client.get(reverse('api:semesters-timeallocations', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 403)

    def test_get_semester_proposals(self):
        response = self.client.get(reverse('api:semesters-proposals', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['id'], self.proposal.id)

    def test_get_semester_proposals_only_returns_active(self):
        self.proposal.active = False
        self.proposal.save()
        response = self.client.get(reverse('api:semesters-proposals', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_get_semester_proposals_only_returns_science_proposals(self):
        self.proposal.non_science = True
        self.proposal.save()
        response = self.client.get(reverse('api:semesters-proposals', kwargs={'pk': self.semesters[0].id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)


class TestMembershipLimitApi(APITestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user_1 = blend_user()
        self.ci_user_2 = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI, time_limit=0)
        Membership.objects.create(user=self.ci_user_1, proposal=self.proposal, role=Membership.CI, time_limit=0)
        Membership.objects.create(user=self.ci_user_2, proposal=self.proposal, role=Membership.CI, time_limit=0)

    def test_set_limit(self):
        self.client.force_login(self.pi_user)
        membership_1 = self.ci_user_1.membership_set.first()
        membership_2 = self.ci_user_2.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership_1.id}),
            data={'time_limit_hours': 1}
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
        other_membership = Membership.objects.create(
            user=other_user, proposal=other_proposal, role=Membership.CI, time_limit=-1
        )
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': other_membership.id}),
            data={'time_limit_hours': 300},
        )
        other_membership.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_membership.time_limit, -1)

    def test_set_bad_time_limit(self):
        self.client.force_login(self.pi_user)
        membership = self.ci_user_1.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership.id}),
            data={'time_limit_hours': ''}
        )
        membership.refresh_from_db()
        self.assertEqual(membership.time_limit, 0)
        self.assertContains(response, 'time_limit_hours', status_code=400)

    def test_membership_id_does_not_exist(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': 12345678}),
            data={'time_limit_hours': 1},
        )
        self.assertEqual(response.status_code, 404)

    def test_ci_cannot_set_limit(self):
        self.client.force_login(self.ci_user_1)
        membership = self.ci_user_1.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership.id}),
            data={'time_limit_hours': 1000},
        )
        membership.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(membership.time_limit, 0)

    def test_nonmember_cannot_set_limit(self):
        self.client.force_login(blend_user())
        membership = self.ci_user_1.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership.id}),
            data={'time_limit_hours': 5},
        )
        membership.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(membership.time_limit, 0)

    def test_must_be_authenticated_to_set_limits(self):
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': self.ci_user_1.id}),
            data={'time_limit_hours': 1},
        )
        self.assertEqual(response.status_code, 403)

    def test_set_no_limit(self):
        self.client.force_login(self.pi_user)
        membership = self.ci_user_1.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership.id}),
            data={'time_limit_hours': -1},
        )
        membership.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(membership.time_limit, -3600)

    def test_cannot_set_the_limit_on_pi_membership(self):
        self.client.force_login(self.pi_user)
        membership = self.pi_user.membership_set.first()
        response = self.client.post(
            reverse('api:memberships-limit', kwargs={'pk': membership.id}),
            data={'time_limit_hours': -1},
        )
        membership.refresh_from_db()
        self.assertContains(response, 'You cannot set the limit on a PI membership', status_code=400)
        self.assertEqual(membership.time_limit, 0)


class TestGlobalMembershipLimitApi(APITestCase):
    def setUp(self) -> None:
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user_1 = blend_user()
        self.ci_user_2 = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI, time_limit=0)
        Membership.objects.create(user=self.ci_user_1, proposal=self.proposal, role=Membership.CI, time_limit=0)
        Membership.objects.create(user=self.ci_user_2, proposal=self.proposal, role=Membership.CI, time_limit=0)

    def test_pi_can_set_globallimit(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 3}
        )
        self.assertContains(response, 'All CI time limits set')
        self.assertEqual(Membership.objects.filter(role=Membership.PI).first().time_limit, 0)
        for membership in Membership.objects.filter(role=Membership.CI):
            self.assertEqual(membership.time_limit, 3 * 3600)

    def test_pi_cannot_set_globallimit_on_other_proposal(self):
        other_proposal = mixer.blend(Proposal)
        other_user = blend_user()
        other_membership = mixer.blend(Membership, user=other_user, proposal=other_proposal, role=Membership.CI)
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': other_proposal.id}),
            data={'time_limit_hours': 3}
        )
        other_membership.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_membership.time_limit, -1)

    def test_ci_cannot_set_globallimit(self):
        self.client.force_login(self.ci_user_1)
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 3}
        )
        self.assertEqual(response.status_code, 403)
        for membership in Membership.objects.all():
            self.assertEqual(membership.time_limit, 0)

    def test_nonmember_cannot_set_globallimit(self):
        self.client.force_login(blend_user())
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 3}
        )
        self.assertEqual(response.status_code, 404)
        for membership in Membership.objects.all():
            self.assertEqual(membership.time_limit, 0)

    def test_unauthenticated_cannot_set_global_limit(self):
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': 3}
        )
        self.assertEqual(response.status_code, 403)
        for membership in Membership.objects.all():
            self.assertEqual(membership.time_limit, 0)

    def test_bad_time_limit(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': None}
        )
        self.assertContains(response, 'time_limit_hours', status_code=400)
        for membership in Membership.objects.all():
            self.assertEqual(membership.time_limit, 0)

    def test_set_no_globallimit(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-globallimit', kwargs={'pk': self.proposal.id}),
            data={'time_limit_hours': -1}
        )
        self.assertEqual(response.status_code, 200)
        for membership in Membership.objects.filter(role=Membership.CI):
            self.assertEqual(membership.time_limit, -3600)


class TestProposalInvitesListApi(APITestCase):
    def setUp(self) -> None:
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        self.first_proposal = mixer.blend(Proposal)
        self.second_proposal = mixer.blend(Proposal)
        self.third_proposal = mixer.blend(Proposal)
        for proposal in [self.first_proposal, self.second_proposal]:
            Membership.objects.create(user=self.pi_user, proposal=proposal, role=Membership.PI)
            Membership.objects.create(user=self.ci_user, proposal=proposal, role=Membership.CI)
            mixer.cycle(3).blend(ProposalInvite, proposal=proposal, used=None, sent=timezone.now())
        mixer.cycle(3).blend(ProposalInvite, proposal=self.third_proposal)

    def test_staff_with_staff_view_can_see_all_proposal_invites(self):
        self.client.force_login(blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True}))
        response = self.client.get(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 9)

    def test_pi_can_see_proposal_invites(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 6)
        for invite in response.json()['results']:
            self.assertTrue(invite['proposal'] in [self.first_proposal.id, self.second_proposal.id])

    def test_pi_can_see_proposal_invites_for_a_proposal(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:invitations-list') + '?proposal=' + self.first_proposal.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 3)
        for invite in response.json()['results']:
            self.assertEqual(invite['proposal'], self.first_proposal.id)

    def test_pi_can_filter_for_pending_invitations(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:invitations-list') + '?pending=true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 6)
        proposalinvite = self.first_proposal.proposalinvite_set.first()
        proposalinvite.used = timezone.now()
        proposalinvite.save()
        response = self.client.get(reverse('api:invitations-list') + '?pending=true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 5)
        response = self.client.get(reverse('api:invitations-list') + '?pending=false')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        self.assertEqual(response.json()['results'][0]['id'], proposalinvite.id)

    def test_unauthenticated_user_not_allowed(self):
        response = self.client.get(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 403)

    def test_ci_cannot_see_proposal_invites(self):
        self.client.force_login(self.ci_user)
        response = self.client.get(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)

    def test_nonmember_cannot_see_proposal_invites(self):
        self.client.force_login(blend_user())
        response = self.client.get(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)

    def test_post_not_allowed(self):
        self.client.force_login(blend_user())
        response = self.client.post(reverse('api:invitations-list'))
        self.assertEqual(response.status_code, 405)


class TestProposalInviteCreateApi(APITestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI)
        Membership.objects.create(user=self.ci_user, proposal=self.proposal, role=Membership.CI)

    def test_unauthenticated_user_not_allowed(self):
        response = self.client.post(reverse('api:proposals-invite', kwargs={'pk': 'someproposal'}))
        self.assertEqual(response.status_code, 403)

    def test_pi_can_send_invite(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': ['rick@getschwifty.com']}
        )
        self.assertTrue(ProposalInvite.objects.filter(email='rick@getschwifty.com', proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)

    def test_pi_can_send_multiple_invites(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': ['rick@getschwifty.com', 'morty@globbitygook.com']},
        )
        self.assertTrue(ProposalInvite.objects.filter(email='rick@getschwifty.com', proposal=self.proposal).exists())
        self.assertTrue(ProposalInvite.objects.filter(email='morty@globbitygook.com', proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)

    def test_cannot_invite_to_other_proposal(self):
        self.client.force_login(blend_user())
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': ['nefarious@evil.com']},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProposalInvite.objects.filter(email='nefarious@evil.com', proposal=self.proposal).exists())

    def test_ci_cannot_send_invite(self):
        self.client.force_login(self.ci_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': ['nefarious@evil.com']},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProposalInvite.objects.filter(email='nefarious@evil.com', proposal=self.proposal).exists())

    def test_invalid_email(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': ['notanemailaddress']},
        )
        self.assertFalse(ProposalInvite.objects.filter(email='notanemailaddress', proposal=self.proposal).exists())
        self.assertContains(response, 'Enter a valid email address', status_code=400)

    def test_pi_cannot_invite_themselves_as_coi(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': [self.pi_user.email]},
        )
        self.assertFalse(ProposalInvite.objects.filter(email=self.pi_user.email, proposal=self.proposal).exists())
        self.assertContains(
            response, f'You cannot invite yourself ({self.pi_user.email}) to be a Co-Investigator', status_code=400
        )

    def test_cannot_invite_user_that_is_already_member(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': [self.ci_user.email]},
        )
        self.assertFalse(ProposalInvite.objects.filter(email=self.ci_user.email, proposal=self.proposal).exists())
        self.assertContains(
            response, f'User with email {self.ci_user.email} is already a member of this proposal', status_code=400
        )

    def test_inviting_a_user_that_already_exists_creates_membership(self):
        self.client.force_login(self.pi_user)
        user = blend_user()
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': [user.email]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProposalInvite.objects.filter(email=user.email, proposal=self.proposal).exists())
        self.assertTrue(Membership.objects.filter(user=user, proposal=self.proposal, role=Membership.CI).exists())

    def test_inviting_user_that_already_has_a_pending_invite_updates_sent_time(self):
        email = 'invite@me.com'
        initial_sent_time = timezone.now() - timedelta(days=1)
        proposal_invite = mixer.blend(
            ProposalInvite,
            sent=initial_sent_time,
            proposal=self.proposal,
            used=None,
            role=Membership.CI,
            email=email
        )
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('api:proposals-invite', kwargs={'pk': self.proposal.id}),
            data={'emails': [email]},
        )
        self.assertEqual(response.status_code, 200)
        proposal_invite.refresh_from_db()
        self.assertTrue(ProposalInvite.objects.filter(pk=proposal_invite.id).exists())
        self.assertGreater(proposal_invite.sent, initial_sent_time)


class TestProposalInviteDetailApi(APITestCase):
    def setUp(self):
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        proposal = mixer.blend(Proposal)
        Membership.objects.create(user=self.pi_user, proposal=proposal, role=Membership.PI)
        Membership.objects.create(user=self.ci_user, proposal=proposal, role=Membership.CI)
        self.proposal_invite = ProposalInvite.objects.create(
            proposal=proposal,
            role=Membership.CI,
            email='inviteme@example.com',
            sent=timezone.now(),
            used=None
        )

    def test_put_not_allowed(self):
        self.client.force_login(blend_user())
        response = self.client.put(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 405)

    def test_patch_not_allowed(self):
        self.client.force_login(blend_user())
        response = self.client.patch(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_user_not_allowed_to_delete_invitation(self):
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': 12345}))
        self.assertEqual(response.status_code, 403)

    def test_pi_can_see_invitation(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.proposal_invite.id)

    def test_ci_cannot_see_invitation(self):
        self.client.force_login(self.ci_user)
        response = self.client.get(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_not_allowed_to_see_invitation(self):
        response = self.client.get(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 403)

    def test_nonmember_cannot_see_invitation(self):
        self.client.force_login(blend_user())
        response = self.client.get(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 404)

    def test_pi_can_delete_invitation(self):
        self.client.force_login(self.pi_user)
        self.assertTrue(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())

    def test_ci_cannot_delete_invitation(self):
        self.client.force_login(self.ci_user)
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())

    def test_nonmember_cannot_delete_invitation(self):
        self.client.force_login(blend_user())
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())

    def test_staff_cannot_delete_invitation(self):
        self.client.force_login(blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True}))
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())

    def test_invitation_that_has_been_used_will_not_be_deleted(self):
        self.proposal_invite.used = timezone.now()
        self.proposal_invite.save()
        self.client.force_login(self.pi_user)
        response = self.client.delete(reverse('api:invitations-detail', kwargs={'pk': self.proposal_invite.id}))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(ProposalInvite.objects.filter(pk=self.proposal_invite.id).exists())


class TestMembershipDetailApi(APITestCase):
    def setUp(self):
        self.pi_user = blend_user()
        self.ci_user_1 = blend_user()
        self.ci_user_2 = blend_user()
        self.proposal = mixer.blend(Proposal)
        self.pim = mixer.blend(Membership, user=self.pi_user, role=Membership.PI, proposal=self.proposal)
        self.cim_1 = mixer.blend(Membership, user=self.ci_user_1, role=Membership.CI, proposal=self.proposal)
        self.cim_2 = mixer.blend(Membership, user=self.ci_user_2, role=Membership.CI, proposal=self.proposal)

    def test_patch_not_allowed(self):
        self.client.force_login(self.pi_user)
        response = self.client.patch(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 405)

    def test_put_not_allowed(self):
        self.client.force_login(self.pi_user)
        response = self.client.put(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_user_get_not_allowed(self):
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': 12345}))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_delete_not_allowed(self):
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': 12345}))
        self.assertEqual(response.status_code, 403)

    def test_pi_can_see_ci_membership(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.cim_1.id)

    def test_ci_can_see_own_membership(self):
        self.client.force_login(self.ci_user_1)
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.cim_1.id)

    def test_ci_cannot_see_other_ci_membership(self):
        self.client.force_login(self.ci_user_1)
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': self.cim_2.id}))
        self.assertEqual(response.status_code, 404)

    def test_nonmember_cannot_see_membership(self):
        self.client.force_login(blend_user())
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_with_staff_view_can_see_membership(self):
        self.client.force_login(blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True}))
        response = self.client.get(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], self.cim_1.id)

    def test_pi_can_delete_ci(self):
        self.client.force_login(self.pi_user)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        self.assertTrue(
            Membership.objects.filter(proposal=self.proposal, user=self.cim_1.user, role=Membership.CI).exists()
        )
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.proposal.membership_set.count(), 2)
        self.assertFalse(
            Membership.objects.filter(proposal=self.proposal, user=self.cim_1.user, role=Membership.CI).exists()
        )

    def test_ci_cannot_delete_other_ci(self):
        other_user = blend_user()
        other_cim = mixer.blend(Membership, user=other_user, proposal=self.proposal, role=Membership.CI)
        self.client.force_login(self.ci_user_1)
        self.assertEqual(self.proposal.membership_set.count(), 4)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': other_cim.id}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.proposal.membership_set.count(), 4)
        self.assertTrue(Membership.objects.filter(proposal=self.proposal, role=Membership.CI, user=other_user).exists())

    def test_ci_cannot_delete_own_membership(self):
        self.client.force_login(self.ci_user_1)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        self.assertTrue(Membership.objects.filter(proposal=self.proposal, role=Membership.CI, user=self.ci_user_1).exists())

    def test_nonmember_cannot_delete_membership(self):
        self.client.force_login(blend_user())
        self.assertEqual(self.proposal.membership_set.count(), 3)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': self.cim_1.id}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        self.assertTrue(Membership.objects.filter(proposal=self.proposal, user=self.cim_1.user, role=Membership.CI).exists())

    def test_pi_cannot_delete_ci_of_other_proposal(self):
        other_proposal = mixer.blend(Proposal)
        other_membership = mixer.blend(Membership, user=self.ci_user_1, proposal=other_proposal, role=Membership.CI)
        self.client.force_login(self.pi_user)
        self.assertEqual(other_proposal.membership_set.count(), 1)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': other_membership.id}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_proposal.membership_set.count(), 1)

    def test_pi_user_cannot_delete_themselves(self):
        self.client.force_login(self.pi_user)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': self.pim.id}))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.proposal.membership_set.count(), 3)

    def test_pi_cannot_delete_another_pi_on_their_own_proposal(self):
        second_pi_membership = mixer.blend(Membership, user=blend_user(), role=Membership.PI, proposal=self.proposal)
        self.client.force_login(self.pi_user)
        self.assertEqual(self.proposal.membership_set.count(), 4)
        response = self.client.delete(reverse('api:memberships-detail', kwargs={'pk': second_pi_membership.id}))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.proposal.membership_set.count(), 4)


class TestMembershipListApi(APITestCase):
    def setUp(self):
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        self.other_pi_user = blend_user()
        self.other_ci_user = blend_user()
        self.first_proposal = mixer.blend(Proposal)
        self.second_proposal = mixer.blend(Proposal)
        self.third_proposal = mixer.blend(Proposal)
        for proposal in [self.first_proposal, self.second_proposal]:
            mixer.blend(Membership, user=self.pi_user, role=Membership.PI, proposal=proposal)
            mixer.blend(Membership, user=self.ci_user, role=Membership.CI, proposal=proposal)

        mixer.blend(Membership, user=self.other_pi_user, role=Membership.PI, proposal=self.third_proposal)
        mixer.blend(Membership, user=self.other_ci_user, role=Membership.CI, proposal=self.third_proposal)

    def test_unauthenticated_user_not_allowed_to_list(self):
        response = self.client.get(reverse('api:memberships-list'))
        self.assertEqual(response.status_code, 403)

    def test_ci_can_see_own_memberships_and_pi_memberships(self):
        for proposal in [self.first_proposal, self.second_proposal]:
            mixer.blend(Membership, user=blend_user(), proposal=proposal, role=Membership.CI)
        self.client.force_login(self.ci_user)
        response = self.client.get(reverse('api:memberships-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 4)
        for membership in response.json()['results']:
            self.assertTrue(membership['username'] in [self.pi_user.username, self.ci_user.username])

    def test_staff_with_staff_view_can_see_all_memberships(self):
        self.client.force_login(blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True}))
        response = self.client.get(reverse('api:memberships-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 6)

    def test_nonmember_cannot_see_memberships(self):
        self.client.force_login(blend_user())
        response = self.client.get(reverse('api:memberships-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)

    def test_pi_can_see_all_memberships_on_their_proposals(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:memberships-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 4)
        for membership in response.json()['results']:
            self.assertTrue(membership['username'] in [self.pi_user.username, self.ci_user.username])

    def test_filter_memberships_for_proposal(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('api:memberships-list') + '?proposal=' + self.first_proposal.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)
        for membership in response.json()['results']:
            self.assertEqual(membership['proposal'], self.first_proposal.id)
