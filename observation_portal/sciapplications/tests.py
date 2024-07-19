from datetime import timedelta

from django.test import TestCase
from mixer.backend.django import mixer
from django_dramatiq.test import DramatiqTestCase
from django.utils import timezone
from django.core import mail

from observation_portal.accounts.test_utils import blend_user
from observation_portal.sciapplications.models import ScienceApplication, Call, TimeRequest, CoInvestigator, Instrument, ScienceApplicationReview, ReviewPanel
from observation_portal.proposals.models import Semester, Membership, ProposalInvite, ScienceCollaborationAllocation


class TestSciAppToProposal(TestCase):
    def setUp(self):
        self.semester = mixer.blend(Semester)
        self.user = blend_user()
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            proposal_type=Call.SCI_PROPOSAL
        )

    def test_create_proposal_from_single_pi(self):
        app = mixer.blend(ScienceApplication, submitter=self.user, pi='')
        it = mixer.blend(Instrument)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app, instrument_types=[it])
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertEqual(proposal.timeallocation_set.first().instrument_types[0], it.code)
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
        user = blend_user()
        app = mixer.blend(ScienceApplication, submitter=self.user, pi=user.email)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())

    def test_create_proposal_with_tags(self):
        user = blend_user()
        app = mixer.blend(ScienceApplication, submitter=self.user, pi=user.email)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())
        self.assertEqual(proposal.tags, app.tags)
        self.assertTrue(len(proposal.tags) == 0)

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
        coi1 = blend_user(user_params={'email': '1@example.com'})
        coi2 = blend_user(user_params={'email': '2@example.com'})
        mixer.blend(CoInvestigator, email='1@example.com', science_application=app)
        mixer.blend(CoInvestigator, email='2@example.com', science_application=app)
        mixer.blend(CoInvestigator, email='3@example.com', science_application=app)
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
        it = mixer.blend(Instrument)
        it2 = mixer.blend(Instrument)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app, instrument_types=[it], semester=self.semester)
        tr2 = mixer.blend(TimeRequest, approved=True, science_application=app, instrument_types=[it2], semester=other_semester)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(self.user, proposal.membership_set.get(role=Membership.PI).user)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())

        self.assertEqual(proposal.timeallocation_set.get(semester=self.semester).std_allocation, tr.std_time)
        self.assertEqual(proposal.timeallocation_set.get(semester=self.semester).instrument_types[0], it.code)

        self.assertEqual(proposal.timeallocation_set.get(semester=other_semester).std_allocation, tr2.std_time)
        self.assertEqual(proposal.timeallocation_set.get(semester=other_semester).instrument_types[0], it2.code)

    def test_create_collab_proposal(self):
        pi = blend_user()
        submitter = blend_user()
        sca = mixer.blend(ScienceCollaborationAllocation, admin=submitter)
        app = mixer.blend(ScienceApplication, submitter=submitter, pi=pi.email)
        tr = mixer.blend(TimeRequest, approved=True, science_application=app)
        proposal = app.convert_to_proposal()
        self.assertEqual(app.proposal, proposal)
        self.assertEqual(pi, proposal.membership_set.get(role=Membership.PI).user)
        self.assertEqual(proposal.sca, sca)
        self.assertEqual(proposal.timeallocation_set.first().std_allocation, tr.std_time)
        self.assertFalse(ProposalInvite.objects.filter(proposal=proposal).exists())


class TestReviewProcess(DramatiqTestCase):

    def setUp(self):
        super().setUp()

        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.SCI_PROPOSAL,
            eligibility_short='Short Eligibility'
        )
        mixer.blend(Instrument, call=self.call)

    def test_email_sent_to_panelists_on_create(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )


        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 3)
        expected_email_subject = f"Proposal Application Review Requested: {app_review.science_application.title}"
        self.assertEqual(set([expected_email_subject]), set(x.subject for x in mail.outbox))
        self.assertEqual(
            set(u.email for u in panel.members.all()),
            set(t for x in mail.outbox for t in x.to)
        )


    def test_email_not_sent_to_panelists_on_update(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)

        self.broker.join('default')
        self.worker.join()

        mail.outbox = []

        app_review.technical_review = "test"
        app_review.save()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)

    def test_application_is_accepted_on_review_accepted(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)
        self.assertEqual(app.status, ScienceApplication.SUBMITTED)

        app_review.status = ScienceApplicationReview.Status.ACCEPTED
        app_review.save()

        self.assertEqual(app.status, ScienceApplication.ACCEPTED)

    def test_application_is_rejected_on_review_rejected(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)
        self.assertEqual(app.status, ScienceApplication.SUBMITTED)

        app_review.status = ScienceApplicationReview.Status.REJECTED
        app_review.save()

        self.assertEqual(app.status, ScienceApplication.REJECTED)

    def test_email_sent_to_submitter_on_accepted(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)

        self.broker.join('default')
        self.worker.join()

        mail.outbox = []

        app_review.status = ScienceApplicationReview.Status.ACCEPTED
        app_review.notify_submitter = True
        app_review.notify_submitter_additional_message = "extra message"
        app_review.save()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [submitter.email])
        self.assertIn("extra message", str(mail.outbox[0].message()))

    def test_email_sent_to_submitter_on_rejected(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)

        self.broker.join('default')
        self.worker.join()

        mail.outbox = []

        app_review.status = ScienceApplicationReview.Status.REJECTED
        app_review.notify_submitter = True
        app_review.notify_submitter_additional_message = "rejected extra message"
        app_review.save()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [submitter.email])
        self.assertEqual(mail.outbox[0].to, [submitter.email])
        self.assertIn("rejected extra message", str(mail.outbox[0].message()))

    def test_email_not_sent_to_submitter_if_flag_disabled(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        user1 = blend_user()
        user2 = blend_user()
        user3 = blend_user()

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([user1, user2, user3])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=user1,
            secondary_reviewer=user2,
        )

        self.assertEqual(app_review.status, ScienceApplicationReview.Status.AWAITING_REVIEWS)

        self.broker.join('default')
        self.worker.join()

        mail.outbox = []

        app_review.status = ScienceApplicationReview.Status.ACCEPTED
        app_review.notify_submitter = False
        app_review.notify_submitter_additional_message = "extra message"
        app_review.save()

        self.broker.join('default')
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)
