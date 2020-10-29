from datetime import timedelta

from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.urls import reverse
from django.utils import timezone

from observation_portal.sciapplications.models import ScienceApplication, Call, CoInvestigator, Instrument, TimeRequest
from observation_portal.proposals.models import Semester, ScienceCollaborationAllocation, CollaborationAllocation
from observation_portal.accounts.test_utils import blend_user


class TestCallAPI(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        now = timezone.now()
        self.open_call = mixer.blend(
            Call, proposal_type=Call.SCI_PROPOSAL, opens=now - timedelta(days=1), deadline=now + timedelta(days=1)
        )
        self.open_collab_call = mixer.blend(
            Call, proposal_type=Call.COLLAB_PROPOSAL, opens=now - timedelta(days=2), deadline=now + timedelta(days=1)
        )
        self.closed_call = mixer.blend(
            Call, proposal_type=Call.SCI_PROPOSAL, opens=now - timedelta(days=2), deadline=now - timedelta(days=1)
        )
        self.future_call = mixer.blend(
            Call, proposal_type=Call.SCI_PROPOSAL, opens=now + timedelta(days=2), deadline=now + timedelta(days=7)
        )
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('api:calls-list'))
        self.assertEqual(response.status_code, 403)

    def test_non_sca_admin_sees_open_non_collab_calls(self):
        response = self.client.get(reverse('api:calls-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], self.open_call.id)
        self.assertContains(response, self.open_call.eligibility_short)

    def test_sca_admin_sees_all_open_calls(self):
        mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        response = self.client.get(reverse('api:calls-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)
        for result in response.json()['results']:
            self.assertTrue(result['id'] in [self.open_call.id, self.open_collab_call.id])


class TestDeleteScienceApplicationAPI(APITestCase):
    def setUp(self):
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.DDT_PROPOSAL
        )
        mixer.blend(Instrument, call=self.call)

    def test_can_delete_draft(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.delete(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ScienceApplication.objects.filter(pk=app.id).exists())

    def test_cannot_delete_non_draft(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=self.user,
            call=self.call
        )
        response = self.client.delete(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(ScienceApplication.objects.filter(pk=app.id).exists())

    def test_cannot_delete_other_users_application(self):
        other_user = blend_user()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=other_user,
            call=self.call
        )
        response = self.client.delete(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ScienceApplication.objects.filter(pk=app.id).exists())

    def test_must_be_authenticated(self):
        self.client.logout()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.delete(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ScienceApplication.objects.filter(pk=app.id).exists())


class TestGetScienceApplicationDetailAPI(APITestCase):
    def setUp(self):
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.SCI_PROPOSAL
        )
        mixer.blend(Instrument, call=self.call)

    def test_can_view_application(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertContains(response, app.title)

    def test_cannot_view_other_users_application(self):
        other_user = blend_user()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=other_user,
            call=self.call
        )
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_view_other_users_application(self):
        staff_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(staff_user)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertNotContains(response, app.title, status_code=404)

    def test_staff_with_staff_view_can_view_other_users_application(self):
        staff_user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(staff_user)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertContains(response, app.title)

    # TODO: Refactor test
    # def test_pdf_view(self):
    #     # Just test the view here, actual pdf rendering is slow and loud
    #     PdfFileMerger.merge = MagicMock
    #     HTML.write_pdf = MagicMock
    #     app = mixer.blend(
    #         ScienceApplication,
    #         status=ScienceApplication.DRAFT,
    #         submitter=self.user,
    #         call=self.call
    #     )
    #     response = self.client.get(reverse('sciapplications:pdf', kwargs={'pk': app.id}))
    #     self.assertTrue(PdfFileMerger.merge.called)
    #     self.assertTrue(HTML.write_pdf.called)
    #     self.assertEqual(response.status_code, 200)

    # TODO: Refactor test
    # def test_staff_can_view_pdf(self):
    #     PdfFileMerger.merge = MagicMock
    #     HTML.write_pdf = MagicMock
    #     staff_user = blend_user(user_params={'is_staff': True})
    #     self.client.force_login(staff_user)
    #     self.client.force_login(staff_user)
    #     app = mixer.blend(
    #         ScienceApplication,
    #         status=ScienceApplication.DRAFT,
    #         submitter=self.user,
    #         call=self.call
    #     )
    #     response = self.client.get(reverse('sciapplications:pdf', kwargs={'pk': app.id}))
    #     self.assertTrue(PdfFileMerger.merge.called)
    #     self.assertTrue(HTML.write_pdf.called)
    #     self.assertEqual(response.status_code, 200)

    # TODO: Refactor test
    # def test_pdf_does_not_include_author_names(self):
    #     PdfFileMerger.merge = MagicMock
    #     HTML.write_pdf = MagicMock
    #     app = mixer.blend(
    #         ScienceApplication,
    #         status=ScienceApplication.SUBMITTED,
    #         submitter=self.user,
    #         call=self.call
    #     )
    #     mixer.cycle(3).blend(CoInvestigator, science_application=app, last_name=mixer.RANDOM)
    #     response = self.client.get(reverse('sciapplications:pdf', kwargs={'pk': app.id}))
    #     self.assertNotContains(response, app.submitter.last_name)
    #     for coi in app.coinvestigator_set.all():
    #         self.assertNotContains(response, coi.last_name)

    # TODO - Test this in the frontend
    def test_detail_does_contain_author_names(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=self.user,
            call=self.call
        )
        mixer.cycle(3).blend(CoInvestigator, science_application=app, last_name=mixer.RANDOM)
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertContains(response, app.submitter.last_name)
        for coi in app.coinvestigator_set.all():
            self.assertContains(response, coi.last_name)


class TestListScienceApplicationAPI(APITestCase):
    def setUp(self):
        super().setUp()
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.SCI_PROPOSAL,
            eligibility_short='Short Eligibility'
        )
        mixer.blend(Instrument, call=self.call)

    def test_unauthorized(self):
        self.client.logout()
        response = self.client.get(reverse('api:scienceapplications-list'))
        self.assertEqual(response.status_code, 403)

    def test_no_applications(self):
        response = self.client.get(reverse('api:scienceapplications-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 0)

    def test_user_can_see_their_application(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('api:scienceapplications-list'))
        self.assertContains(response, app.title)
        self.assertEqual(response.json()['count'], 1)

    # TODO - Refactor and also test this in the frontend
    # def test_collab_admin_time_used(self):
    #     call = mixer.blend(
    #         Call, semester=self.semester,
    #         deadline=timezone.now() + timedelta(days=7),
    #         opens=timezone.now(),
    #         proposal_type=Call.COLLAB_PROPOSAL,
    #     )
    #     sca = mixer.blend(ScienceCollaborationAllocation, admin=self.user)
    #     ca = mixer.blend(CollaborationAllocation, sca=sca, telescope_name='1 meter', allocation=9)
    #     app = mixer.blend(
    #         ScienceApplication,
    #         status=ScienceApplication.DRAFT,
    #         submitter=self.user,
    #         call=call
    #     )
    #     instrument = mixer.blend(Instrument, code='1M0-SCICAM-SBIG')
    #     tr = mixer.blend(TimeRequest, science_application=app, instrument=instrument, std_time=8)
    #     response = self.client.get(reverse('sciapplications:index'))
    #     self.assertContains(response, '{0}/{1}'.format(tr.std_time, ca.allocation))
