from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from mixer.backend.django import mixer
from django.utils import timezone

from observation_portal.proposals.models import Membership, Proposal, ProposalInvite
from observation_portal.proposals.models import Semester, TimeAllocation, ScienceCollaborationAllocation
from observation_portal.accounts.models import Profile
from observation_portal.accounts.test_utils import blend_user


class TestProposalDetail(TestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI)
        Membership.objects.create(user=self.ci_user, proposal=self.proposal, role=Membership.CI)

    def test_proposal_detail_as_pi(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)

    def test_proposal_detail_as_ci(self):
        self.client.force_login(self.ci_user)
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)
        self.assertNotContains(response, 'Pending Invitations')

    def test_proposal_detail_as_staff(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, self.proposal.id)

    def test_proposal_detail_unauthenticated(self):
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 302)

    def test_show_pending_invites(self):
        invite = mixer.blend(ProposalInvite, used=None, proposal=self.proposal)
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertContains(response, invite.email)

    def test_proposal_as_ci_cant_see_cis(self):
        other_ci_user = mixer.blend(User)
        mixer.blend(Profile, user=other_ci_user)
        Membership.objects.create(user=other_ci_user, proposal=self.proposal, role=Membership.CI)

        self.client.force_login(self.ci_user)
        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal.id}))
        self.assertNotContains(response, other_ci_user.email)


class TestProposalInvite(TestCase):
    def setUp(self):
        self.proposal = mixer.blend(Proposal)
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        Membership.objects.create(user=self.pi_user, proposal=self.proposal, role=Membership.PI)
        Membership.objects.create(user=self.ci_user, proposal=self.proposal, role=Membership.CI)

    def test_invite(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': 'rick@getschwifty.com'},
            follow=True
        )
        self.assertTrue(ProposalInvite.objects.filter(email='rick@getschwifty.com', proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)

    def test_multiple_invite(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': 'rick@getschwifty.com, morty@globbitygook.com, '},
            follow=True
        )
        self.assertTrue(ProposalInvite.objects.filter(email='rick@getschwifty.com', proposal=self.proposal).exists())
        self.assertTrue(ProposalInvite.objects.filter(email='morty@globbitygook.com', proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)

    def test_invite_get(self):
        self.client.force_login(self.pi_user)
        response = self.client.get(reverse('proposals:invite', kwargs={'pk': self.proposal.id}))
        self.assertEqual(response.status_code, 405)

    def test_cannot_invite_to_other_proposal(self):
        self.client.force_login(blend_user())
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': 'nefarious@evil.com'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProposalInvite.objects.filter(email='nefarious@evil.com', proposal=self.proposal).exists())

    def test_ci_cannot_invite(self):
        self.client.force_login(self.ci_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': 'nefarious@evil.com'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProposalInvite.objects.filter(email='nefarious@evil.com', proposal=self.proposal).exists())

    def test_validate_email(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': 'notanemailaddress'},
            follow=True
        )
        self.assertFalse(ProposalInvite.objects.filter(email='notanemailaddress', proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a valid email address')

    def test_pi_cannot_invite_themselves_as_coi(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': self.pi_user.email},
            follow=True
        )
        self.assertFalse(ProposalInvite.objects.filter(email=self.pi_user.email, proposal=self.proposal).exists())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'You cannot invite yourself ({self.pi_user.email}) to be a Co-Investigator')

    def test_cannot_invite_user_that_is_already_member(self):
        self.client.force_login(self.pi_user)
        response = self.client.post(
            reverse('proposals:invite', kwargs={'pk': self.proposal.id}),
            data={'email': self.ci_user.email},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'User with email {self.ci_user.email} is already a member of this proposal')


class TestProposalList(TestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposals = mixer.cycle(5).blend(Proposal)
        for proposal in self.proposals:
            mixer.blend(Membership, user=self.user, proposal=proposal)

    def test_no_proposals(self):
        user = blend_user()
        self.client.force_login(user)
        response = self.client.get(reverse('proposals:list'))
        self.assertContains(response, 'You are not a member of any proposals')
        self.assertNotContains(response, 'Admin only')

    def test_no_proposals_for_semester(self):
        user = blend_user()
        semester = mixer.blend(Semester, id='2016A')
        other_semester = mixer.blend(Semester, id='2017A')
        proposal = mixer.blend(Proposal)
        mixer.blend(TimeAllocation, semester=semester)
        mixer.blend(Membership, user=user, proposal=proposal)
        self.client.force_login(user)

        response = self.client.get(reverse('proposals:list') + '?semester={}'.format(other_semester.id))
        self.assertContains(response, 'No proposals for this semester.')

    def test_proposals_show_in_list(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('proposals:list'))
        for proposal in self.proposals:
            self.assertContains(response, proposal.id)

    def test_admin_link(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse('proposals:list'))
        self.assertContains(response, 'Admin only')


class TestProposalInviteDelete(TestCase):
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

    def test_delete_proposal_invite_pi(self):
        self.client.force_login(self.pi_user)

        response = self.client.get(reverse('proposals:detail', kwargs={'pk': self.proposal_invite.proposal.id}))
        self.assertContains(response, self.proposal_invite.email)

        response = self.client.post(
            reverse('proposals:proposalinvite-delete', kwargs={'pk': self.proposal_invite.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.proposal_invite.email)

    def test_ci_cannot_delete_invitation(self):
        self.client.force_login(self.ci_user)
        response = self.client.post(
            reverse('proposals:proposalinvite-delete', kwargs={'pk': self.proposal_invite.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)


class TestMembershipDelete(TestCase):
    def setUp(self):
        self.pi_user = blend_user()
        self.ci_user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.pi_user, role=Membership.PI, proposal=self.proposal)
        self.cim = mixer.blend(Membership, user=self.ci_user, role=Membership.CI, proposal=self.proposal)

    def test_pi_can_remove_ci(self):
        self.client.force_login(self.pi_user)

        self.assertEqual(self.proposal.membership_set.count(), 2)
        response = self.client.post(
            reverse('proposals:membership-delete', kwargs={'pk': self.cim.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.proposal.membership_set.count(), 1)

    def test_ci_cannot_remove_ci(self):
        other_user = blend_user()
        other_cim = mixer.blend(Membership, user=other_user, proposal=self.proposal)

        self.client.force_login(self.ci_user)
        self.assertEqual(self.proposal.membership_set.count(), 3)
        response = self.client.post(
            reverse('proposals:membership-delete', kwargs={'pk': other_cim.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.proposal.membership_set.count(), 3)

    def test_pi_cannot_remove_ci_other_proposal(self):
        other_proposal = mixer.blend(Proposal)
        other_membership = mixer.blend(Membership, user=self.ci_user, proposal=other_proposal)

        self.client.force_login(self.pi_user)
        self.assertEqual(other_proposal.membership_set.count(), 1)
        response = self.client.post(
            reverse('proposals:membership-delete', kwargs={'pk': other_membership.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_proposal.membership_set.count(), 1)


class TestSemesterAdmin(TestCase):
    def setUp(self):
        self.user = blend_user(user_params={'is_staff': True})
        self.proposal = mixer.blend(Proposal)
        self.semester = mixer.blend(Semester)
        self.ta = mixer.blend(TimeAllocation, semester=self.semester, proposal=self.proposal)

    def test_proposal_table(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('proposals:semester-admin', kwargs={'pk': self.semester.id})
        )
        self.assertContains(response, self.proposal.id)

    def test_proposal_table_not_staff(self):
        user = blend_user()
        self.client.force_login(user)
        response = self.client.get(
            reverse('proposals:semester-admin', kwargs={'pk': self.semester.id})
        )
        self.assertEqual(response.status_code, 403)


class TestSemesterDetail(TestCase):
    def setUp(self):
        sca = mixer.blend(ScienceCollaborationAllocation)
        self.proposal = mixer.blend(Proposal, sca=sca)
        self.semester = mixer.blend(Semester)
        self.ta = mixer.blend(TimeAllocation, semester=self.semester, proposal=self.proposal)

    def test_view_summary(self):
        response = self.client.get(reverse('proposals:semester-detail', kwargs={'pk': self.semester.id}))
        self.assertContains(response, self.proposal.title)

    def test_current_redirect(self):
        response = self.client.get(reverse('proposals:semester-current'))
        self.assertEqual(response.status_code, 302)
