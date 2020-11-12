from datetime import timedelta
from os import urandom
from unittest.mock import patch

from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from django_dramatiq.test import DramatiqTestCase
from django.test.client import MULTIPART_CONTENT, BOUNDARY, encode_multipart

from observation_portal.sciapplications.models import ScienceApplication, Call, CoInvestigator, Instrument, TimeRequest
from observation_portal.proposals.models import Semester, ScienceCollaborationAllocation, CollaborationAllocation
from observation_portal.accounts.test_utils import blend_user
from observation_portal.sciapplications.serializers import ScienceApplicationCreateSerializer


class MockPDFFileReader:
    def __init__(self, bytesio):
        self.content = bytesio.getvalue()

    def getNumPages(self):
        return len(self.content)


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

    # TODO: This needs to be done on the frontend if we are generating the combined pdf there
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

    # TODO: This needs to be done on the frontend if we are generating the combined pdf there
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

    # TODO: This needs to be done on the frontend if we are generating the combined pdf there
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

    # TODO - Test this in the frontend, but this also works as a check on the API endpoint
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

    def test_detail_contains_time_requested_in_scicollab_app_by_telescope_name(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.COLLAB_PROPOSAL,
        )
        sca = mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        mixer.blend(CollaborationAllocation, sca=sca, telescope_name='1 meter', allocation=9)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=call
        )
        instrument = mixer.blend(Instrument, code='1M0-SCICAM-SBIG')
        # The time request is made for an instrument, but the collaboration allocation is set per
        # telescope class. They are matched up by the names in configdb.
        mixer.blend(TimeRequest, science_application=app, instrument=instrument, std_time=8)
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.json()['timerequest_set'][0]['std_time'], 8)
        self.assertEqual(response.json()['timerequest_set'][0]['telescope_name'], '1 meter')


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

    # TODO - Test this in the frontend
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


@patch('observation_portal.sciapplications.serializers.PdfFileReader', new=MockPDFFileReader)
class TestPostCreateSciApp(DramatiqTestCase):
    def setUp(self):
        super().setUp()
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.instrument = mixer.blend(Instrument)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL,
            instruments=(self.instrument,)
        )
        self.key_call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.KEY_PROPOSAL,
            instruments=(self.instrument,)
        )
        self.ddt_call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.DDT_PROPOSAL,
            instruments=(self.instrument,)
        )
        self.collab_call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.COLLAB_PROPOSAL,
            instruments=(self.instrument,)
        )
        data = {
            'call': self.call.id,
            'status': 'SUBMITTED',
            'title': 'Test Title',
            'pi': 'test@example.com',
            'pi_first_name': 'Joe',
            'pi_last_name': 'Schmoe',
            'pi_institution': 'Walmart',
            'pdf': SimpleUploadedFile('s.pdf', b'ab'),
            'abstract': 'test abstract value',
            'tac_rank': 1
        }
        timerequest_data = {
            'timerequest_set[0]id': '',
            'timerequest_set[0]instrument': self.instrument.id,
            'timerequest_set[0]semester': self.semester.id,
            'timerequest_set[0]std_time': 30,
            'timerequest_set[0]rr_time': 1,
            'timerequest_set[0]tc_time': 5,
        }
        ci_data = {
            'coinvestigator_set[0]id': '',
            'coinvestigator_set[0]email': 'bilbo@baggins.com',
            'coinvestigator_set[0]first_name': 'Bilbo',
            'coinvestigator_set[0]last_name': 'Baggins',
            'coinvestigator_set[0]institution': 'lco',
        }
        self.sci_data = {
            k: data[k] for k in data
            if k in ScienceApplicationCreateSerializer.get_required_fields_for_submission(Call.SCI_PROPOSAL)
        }
        self.sci_data.update(timerequest_data)
        self.sci_data.update(ci_data)
        self.key_data = {
            k: data[k] for k in data
            if k in ScienceApplicationCreateSerializer.get_required_fields_for_submission(Call.KEY_PROPOSAL)
        }
        self.key_data['call'] = self.key_call.id
        self.key_data.update(timerequest_data)
        self.key_data.update(ci_data)
        self.ddt_data = {
            k: data[k] for k in data
            if k in ScienceApplicationCreateSerializer.get_required_fields_for_submission(Call.DDT_PROPOSAL)
        }
        self.ddt_data['call'] = self.ddt_call.id
        self.ddt_data.update(timerequest_data)
        self.ddt_data.update(ci_data)
        self.collab_data = {
            k: data[k] for k in data
            if k in ScienceApplicationCreateSerializer.get_required_fields_for_submission(Call.COLLAB_PROPOSAL)
        }
        self.collab_data['call'] = self.collab_call.id
        self.collab_data.update(timerequest_data)
        self.collab_data.update(ci_data)

    def test_post_sci_form(self):
        good_data = self.sci_data.copy()
        good_data['call'] = self.call.id
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_post_key_form(self):
        good_data = self.key_data.copy()
        good_data['call'] = self.key_call.id
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.key_data['title'], status_code=201)

    def test_post_key_form_multiple_semesters(self):
        good_data = self.key_data.copy()
        good_data['call'] = self.key_call.id
        other_semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        good_data['timerequest_set[1]id'] = '',
        good_data['timerequest_set[1]semester'] = other_semester.id
        good_data['timerequest_set[1]instrument'] = self.instrument.id,
        good_data['timerequest_set[1]std_time'] = 30,
        good_data['timerequest_set[1]rr_time'] = 1,
        good_data['timerequest_set[1]tc_time'] = 5,
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.user.scienceapplication_set.first().timerequest_set.filter(semester=self.semester).exists())
        self.assertTrue(self.user.scienceapplication_set.first().timerequest_set.filter(semester=other_semester).exists())

    def test_post_ddt_form(self):
        good_data = self.ddt_data.copy()
        good_data['call'] = self.ddt_call.id
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.ddt_data['title'], status_code=201)

    def test_post_collab_form(self):
        good_data = self.collab_data.copy()
        good_data['call'] = self.collab_call.id
        mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.collab_data['title'], status_code=201)

    def test_normal_user_post_collab_form(self):
        bad_data = self.collab_data.copy()
        bad_data['call'] = self.collab_call.id
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=bad_data)
        self.assertEqual(num_apps, self.user.scienceapplication_set.count())
        self.assertContains(response, 'object does not exist', status_code=400)

    def test_can_save_incomplete(self):
        data = self.sci_data.copy()
        data['status'] = 'DRAFT'
        data['call'] = self.call.id
        del data['abstract']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().abstract, '')
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.DRAFT)
        self.assertEqual(response.status_code, 201)

    def test_cannot_submit_incomplete(self):
        data = self.sci_data.copy()
        del data['abstract']
        data['call'] = self.call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertEqual(response.json().get('abstract', [''])[0], 'This field is required.')

    def test_multiple_time_requests(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        data.update({
            'timerequest_set[1]id': '',
            'timerequest_set[1]instrument': self.instrument.id,
            'timerequest_set[1]semester': self.semester.id,
            'timerequest_set[1]std_time': 20,
            'timerequest_set[1]rr_time': 10,
            'timerequest_set[1]tc_time': 5,
        })
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().timerequest_set.count(), 2)
        self.assertEqual(response.status_code, 201)

    def test_multiple_coi(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        data.update({
            'coinvestigator_set[1]id': '',
            'coinvestigator_set[1]email': 'frodo@baggins.com',
            'coinvestigator_set[1]first_name': 'Frodo',
            'coinvestigator_set[1]last_name': 'Baggins',
            'coinvestigator_set[1]institution': 'lco',
        })
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().coinvestigator_set.count(), 2)
        self.assertEqual(response.status_code, 201)

    def test_can_post_own_email(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        data['pi'] = self.user.email
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().pi, self.user.email)
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.SUBMITTED)
        self.assertEqual(response.status_code, 201)

    def test_extra_pi_data_required(self):
        bad_data = self.sci_data.copy()
        del bad_data['pi_first_name']
        bad_data['call'] = self.call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=bad_data)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertEqual(response.json().get('pi_first_name', [''])[0], 'This field is required.')
        self.assertEqual(response.status_code, 400)

    def test_can_leave_out_pi_in_draft(self):
        data = self.sci_data.copy()
        data['status'] = 'DRAFT'
        data['call'] = self.call.id
        del data['pi']
        del data['pi_first_name']
        del data['pi_last_name']
        del data['pi_institution']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.user.scienceapplication_set.last().pi, '')

    def test_cannot_leave_out_pi_in_submission(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        del data['pi']
        del data['pi_first_name']
        del data['pi_last_name']
        del data['pi_institution']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertEqual(response.json().get('pi', [''])[0], 'This field is required.')
        self.assertEqual(response.json().get('pi_first_name', [''])[0], 'This field is required.')
        self.assertEqual(response.json().get('pi_last_name', [''])[0], 'This field is required.')
        self.assertEqual(response.json().get('pi_institution', [''])[0], 'This field is required.')

        self.assertEqual(response.status_code, 400)

    def test_cannot_upload_silly_files(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        data['pdf'] = SimpleUploadedFile('notpdf.png', b'apngfile')
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertContains(response, 'We can only accept PDF files', status_code=400)

    def test_submitting_ddt_sends_notification_email(self):
        data = self.ddt_data.copy()
        data['call'] = self.ddt_call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(data['title'], str(mail.outbox[0].message()))
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_draft_ddt_does_not_send_notification_email(self):
        data = self.ddt_data.copy()
        data['call'] = self.ddt_call.id
        data['status'] = ScienceApplication.DRAFT
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)

        self.broker.join("default")
        self.worker.join()

        self.assertEqual(len(mail.outbox), 0)

    def test_submitting_sets_submitted_date(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertIsNotNone(self.user.scienceapplication_set.first().submitted)
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_draft_does_not_set_submitted_date(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        data['status'] = ScienceApplication.DRAFT
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertIsNone(self.user.scienceapplication_set.first().submitted)
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_pdf_has_too_many_pages(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        pdf_data = urandom(1000)
        data['pdf'] = SimpleUploadedFile('s.pdf', pdf_data)
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'PDF file cannot exceed', status_code=400)

    def test_cannot_set_noneligible_semester(self):
        data = self.sci_data.copy()
        data['call'] = self.call.id
        semester = mixer.blend(
            Semester, id='2000BC', start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data['timerequest_set[0]semester'] = semester.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)


@patch('observation_portal.sciapplications.serializers.PdfFileReader', new=MockPDFFileReader)
class TestPostUpdateSciApp(DramatiqTestCase):
    def setUp(self):
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL
        )
        self.instrument = mixer.blend(Instrument, call=self.call)
        self.call.instruments.add(self.instrument)
        self.app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        tr = mixer.blend(TimeRequest, science_application=self.app)
        coi = mixer.blend(CoInvestigator, science_application=self.app)
        self.data = {
            'call': self.call.id,
            'title': 'updates',
            'status': 'DRAFT',
            'timerequest_set[0]id': tr.id,
            'timerequest_set[0]instrument': self.instrument.id,
            'timerequest_set[0]semester': self.semester.id,
            'timerequest_set[0]std_time': tr.std_time,
            'timerequest_set[0]rr_time': tr.rr_time,
            'timerequest_set[0]tc_time': tr.tc_time,
            'coinvestigator_set[0]id': coi.id,
            'coinvestigator_set[0]email': coi.email,
            'coinvestigator_set[0]first_name': coi.first_name,
            'coinvestigator_set[0]last_name': coi.last_name,
            'coinvestigator_set[0]institution': coi.institution
        }

    def test_can_update_draft(self):
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.app.id}),
            data=encode_multipart(BOUNDARY, self.data),
            content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScienceApplication.objects.get(pk=self.app.id).title, self.data['title'])
        self.assertIsNone(ScienceApplication.objects.get(pk=self.app.id).submitted)

    def test_can_submit_draft(self):
        data = self.data.copy()
        data_complete = {
            'status': 'SUBMITTED',
            'pi': 'test@example.com',
            'pi_first_name': 'Joe',
            'pi_last_name': 'Schmoe',
            'pi_institution': 'Walmart',
            'abstract': 'test abstract value',
            'pdf': SimpleUploadedFile('sci.pdf', b'ab'),
        }
        data = {**data, **data_complete}
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.app.id}),
            data=encode_multipart(BOUNDARY, data),
            content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScienceApplication.objects.get(pk=self.app.id).title, data['title'])
        self.assertTrue(ScienceApplication.objects.get(pk=self.app.id).submitted)
