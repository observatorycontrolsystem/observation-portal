from django.test import TestCase
from django.contrib.auth.models import User
from mixer.backend.django import mixer

from observation_portal.sciapplications.models import ScienceApplication, Call, TimeRequest, CoInvestigator
from observation_portal.proposals.models import Semester, Membership, ProposalInvite, ScienceCollaborationAllocation


class TestSciAppToProposal(TestCase):
    def setUp(self):
        self.semester = mixer.blend(Semester)
        self.user = mixer.blend(User)
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            proposal_type=Call.SCI_PROPOSAL
        )

    def test_create_proposal_from_single_pi(self):
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='')
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertEqual(proposal.timeallocation_set.first().instrument_type, tr.instrument.code)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())

    def test_create_proposal_with_supplied_noexistant_pi(self):
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='frodo@example.com')
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertFalse(proposal.membership_set.all())
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertTrue(ProposalInvite.objects.filter(proposal=proposal, role=Membership.PI).exists())

    def test_create_proposal_with_supplied_existant_pi(self):
        user = mixer.blend(User)
        app = mixer.blend(ScienceApplication, submitter=self.user, pi=user.email)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())

    def test_create_proposal_with_nonexistant_cois(self):
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='')
        mixer.cycle(3).blend(CoInvestigator, science_application=app)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertEqual(ProposalInvite.objects.filter(proposal=proposal).count(), 3)

    def test_create_proposal_with_existant_cois(self):
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='')
        coi1 = mixer.blend(User, email='1@lcogt.net')
        coi2 = mixer.blend(User, email='2@lcogt.net')
        mixer.blend(CoInvestigator, email='1@lcogt.net', science_application=app)
        mixer.blend(CoInvestigator, email='2@lcogt.net', science_application=app)
        mixer.blend(CoInvestigator, email='3@lcogt.net', science_application=app)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertEqual(ProposalInvite.objects.filter(proposal=proposal).count(), 1)
        self.assertTrue(proposal.membership_set.filter(role=Membership.CI).filter(user__email=coi1.email).exists())
        self.assertTrue(proposal.membership_set.filter(role=Membership.CI).filter(user__email=coi2.email).exists())

    def test_create_key_proposal_multiple_semesters(self):
        other_semester = mixer.blend(Semester)
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='')
        tr = mixer.blend(TimeRequest, approved=True, science_application=app, semester=self.semester)
        tr2 = mixer.blend(TimeRequest, approved=True, science_application=app, semester=other_semester)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())

        self.assertEqual(proposal.timeallocation_set.get(semester=self.semester).std_allocation, tr.std_time)
        self.assertEqual(proposal.timeallocation_set.get(semester=self.semester).instrument_type, tr.instrument.code)

        self.assertEqual(proposal.timeallocation_set.get(semester=other_semester).std_allocation, tr2.std_time)
        self.assertEqual(proposal.timeallocation_set.get(semester=other_semester).instrument_type, tr2.instrument.code)

    def test_create_collab_proposal(self):
        pi = mixer.blend(User)
        submitter = mixer.blend(User)
        sca = mixer.blend(ScienceCollaborationAllocation, admin=submitter)
        app = mixer.blend(ScienceApplication, submitter=submitter, pi=pi.email)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(pi, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.sca, sca)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())
