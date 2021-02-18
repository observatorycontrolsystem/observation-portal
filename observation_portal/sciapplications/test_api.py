from datetime import timedelta
from os import path
from unittest.mock import patch

from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from django_dramatiq.test import DramatiqTestCase
from django.test.client import MULTIPART_CONTENT, BOUNDARY, encode_multipart
from faker import Faker

from observation_portal.sciapplications.models import ScienceApplication, Call, CoInvestigator, Instrument, TimeRequest
from observation_portal.proposals.models import Semester, ScienceCollaborationAllocation, CollaborationAllocation
from observation_portal.accounts.test_utils import blend_user
from observation_portal.sciapplications.serializers import ScienceApplicationSerializer

fake = Faker()


def generate_time_request_data(index, instrument, semester):
    return {
        f'timerequest_set[{index}]instrument': instrument.id,
        f'timerequest_set[{index}]semester': semester.id,
        f'timerequest_set[{index}]std_time': fake.random_int(min=0, max=100),
        f'timerequest_set[{index}]rr_time': fake.random_int(min=0, max=100),
        f'timerequest_set[{index}]tc_time': fake.random_int(min=0, max=100)
    }


def generate_coinvestigator_data(index):
    return {
        f'coinvestigator_set[{index}]email': fake.email(),
        f'coinvestigator_set[{index}]first_name': fake.first_name(),
        f'coinvestigator_set[{index}]last_name': fake.last_name(),
        f'coinvestigator_set[{index}]institution': fake.company()
    }


class MockPDFFileReader:
    def __init__(self, bytesio):
        self.content = bytesio.getvalue()


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
        response = self.client.get(reverse('api:calls-list') + '?only_open=true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], self.open_call.id)
        self.assertContains(response, self.open_call.eligibility_short)

    def test_sca_admin_sees_all_open_calls(self):
        mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        response = self.client.get(reverse('api:calls-list') + '?only_open=true')
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


@patch('observation_portal.sciapplications.serializers.PdfFileReader', new=MockPDFFileReader)
class TestPostCreateSciApp(DramatiqTestCase):
    def setUp(self):
        super().setUp()
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.scicollab_admin = blend_user()
        mixer.blend(ScienceCollaborationAllocation, admin=self.scicollab_admin)
        self.client.force_login(self.user)
        self.instrument = mixer.blend(Instrument)
        self.other_instrument = mixer.blend(Instrument)
        self.closed_call = mixer.blend(
            Call, semester=self.semester,
            opens=timezone.now() - timedelta(days=14),
            deadline=timezone.now() - timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL,
            instruments=(self.instrument, self.other_instrument)
        )
        self.sci_call = mixer.blend(
            Call, semester=self.semester,
            opens=timezone.now() - timedelta(days=7),
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL,
            instruments=(self.instrument, self.other_instrument)
        )
        self.key_call = mixer.blend(
            Call, semester=self.semester,
            opens=timezone.now() - timedelta(days=7),
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.KEY_PROPOSAL,
            instruments=(self.instrument, self.other_instrument)
        )
        self.ddt_call = mixer.blend(
            Call, semester=self.semester,
            opens=timezone.now() - timedelta(days=7),
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.DDT_PROPOSAL,
            instruments=(self.instrument, self.other_instrument)
        )
        self.collab_call = mixer.blend(
            Call, semester=self.semester,
            opens=timezone.now() - timedelta(days=7),
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.COLLAB_PROPOSAL,
            instruments=(self.instrument, self.other_instrument)
        )
        data = {
            'status': ScienceApplication.SUBMITTED,
            'title': fake.text(max_nb_chars=50),
            'pi': fake.email(),
            'pi_first_name': fake.first_name(),
            'pi_last_name': fake.last_name(),
            'pi_institution': fake.company(),
            'pdf': SimpleUploadedFile('s.pdf', b'ab'),
            'abstract': fake.text(),
            'tac_rank': 1
        }
        timerequest_data = generate_time_request_data(0, self.instrument, self.semester)
        ci_data = generate_coinvestigator_data(0)
        self.sci_data = {
            k: data[k] for k in data
            if k in ScienceApplicationSerializer.get_required_fields_for_submission(Call.SCI_PROPOSAL)
        }
        self.sci_data['call_id'] = self.sci_call.id
        self.sci_data.update(timerequest_data)
        self.sci_data.update(ci_data)
        self.key_data = {
            k: data[k] for k in data
            if k in ScienceApplicationSerializer.get_required_fields_for_submission(Call.KEY_PROPOSAL)
        }
        self.key_data['call_id'] = self.key_call.id
        self.key_data.update(timerequest_data)
        self.key_data.update(ci_data)
        self.ddt_data = {
            k: data[k] for k in data
            if k in ScienceApplicationSerializer.get_required_fields_for_submission(Call.DDT_PROPOSAL)
        }
        self.ddt_data['call_id'] = self.ddt_call.id
        self.ddt_data.update(timerequest_data)
        self.ddt_data.update(ci_data)

        self.collab_data = {
            k: data[k] for k in data
            if k in ScienceApplicationSerializer.get_required_fields_for_submission(Call.COLLAB_PROPOSAL)
        }
        self.collab_data['call_id'] = self.collab_call.id
        self.collab_data.update(timerequest_data)
        self.collab_data.update(ci_data)

    def test_must_be_authenticated(self):
        self.client.logout()
        good_data = self.sci_data.copy()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(response.status_code, 403)

    def test_post_sci_form(self):
        good_data = self.sci_data.copy()
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_post_key_form(self):
        good_data = self.key_data.copy()
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.key_data['title'], status_code=201)

    def test_post_key_form_multiple_semesters(self):
        other_semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        good_data = {**self.key_data.copy(), **generate_time_request_data(1, self.instrument, other_semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        timerequests = self.user.scienceapplication_set.first().timerequest_set
        self.assertEqual(response.status_code, 201)
        self.assertEqual(timerequests.count(), 2)
        self.assertTrue(timerequests.filter(semester=self.semester).exists())
        self.assertTrue(timerequests.filter(semester=other_semester).exists())

    def test_post_ddt_form(self):
        good_data = self.ddt_data.copy()
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.ddt_data['title'], status_code=201)

    def test_post_collab_form(self):
        self.client.force_login(self.scicollab_admin)
        good_data = self.collab_data.copy()
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=good_data)
        self.assertEqual(num_apps + 1, self.scicollab_admin.scienceapplication_set.count())
        self.assertContains(response, self.collab_data['title'], status_code=201)

    def test_normal_user_post_collab_form(self):
        bad_data = self.collab_data.copy()
        num_apps = self.user.scienceapplication_set.count()
        response = self.client.post(reverse('api:scienceapplications-list'), data=bad_data)
        self.assertEqual(num_apps, self.user.scienceapplication_set.count())
        self.assertContains(response, 'object does not exist', status_code=400)

    def test_can_save_incomplete(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.DRAFT
        del data['abstract']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().abstract, '')
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.DRAFT)
        self.assertEqual(response.status_code, 201)

    def test_cannot_submit_incomplete(self):
        data = self.sci_data.copy()
        del data['abstract']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertEqual(response.json().get('abstract', [''])[0], 'This field is required.')

    def test_multiple_time_requests(self):
        # Add another time request
        data = {**self.sci_data.copy(), **generate_time_request_data(1, self.other_instrument, self.semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.user.scienceapplication_set.last().timerequest_set.count(), 2)

    def test_cannot_create_duplicate_time_requests(self):
        # Add a duplicate time request
        data = {**self.sci_data.copy(), **generate_time_request_data(1, self.instrument, self.semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(
            response, 'more than one time request for the same semester and instrument', status_code=400
        )
        self.assertEqual(self.user.scienceapplication_set.count(), 0)

    def test_multiple_coi(self):
        data = {**self.sci_data.copy(), **generate_coinvestigator_data(1)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().coinvestigator_set.count(), 2)
        self.assertEqual(response.status_code, 201)

    def test_can_post_own_email(self):
        data = self.sci_data.copy()
        data['pi'] = self.user.email
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.last().pi, self.user.email)
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.SUBMITTED)
        self.assertEqual(response.status_code, 201)

    def test_extra_pi_data_required(self):
        bad_data = self.sci_data.copy()
        del bad_data['pi_first_name']
        response = self.client.post(reverse('api:scienceapplications-list'), data=bad_data)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertEqual(response.json().get('pi_first_name', [''])[0], 'This field is required.')
        self.assertEqual(response.status_code, 400)

    def test_can_leave_out_pi_in_draft(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.DRAFT
        del data['pi']
        del data['pi_first_name']
        del data['pi_last_name']
        del data['pi_institution']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.user.scienceapplication_set.last().pi, '')

    def test_cannot_leave_out_pi_in_submission(self):
        data = self.sci_data.copy()
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

    def test_cannot_upload_files_that_arent_pdfs(self):
        data = self.sci_data.copy()
        data['pdf'] = SimpleUploadedFile('notpdf.png', b'apngfile')
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(self.user.scienceapplication_set.count(), 0)
        self.assertContains(response, 'We can only accept PDF files', status_code=400)

    def test_submitting_ddt_sends_notification_email(self):
        data = self.ddt_data.copy()
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(data['title'], str(mail.outbox[0].message()))
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_draft_ddt_does_not_send_notification_email(self):
        data = self.ddt_data.copy()
        data['status'] = ScienceApplication.DRAFT
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 0)

    def test_submitting_non_ddt_does_not_send_email(self):
        data = self.sci_data.copy()
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 0)

    def test_submitting_sets_submitted_date(self):
        data = self.sci_data.copy()
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertIsNotNone(self.user.scienceapplication_set.first().submitted)
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_draft_does_not_set_submitted_date(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.DRAFT
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertIsNone(self.user.scienceapplication_set.first().submitted)
        self.assertContains(response, self.sci_data['title'], status_code=201)

    def test_cannot_set_noneligible_semester(self):
        semester = mixer.blend(
            Semester, id='2000BC', start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data = {**self.sci_data.copy(), **generate_time_request_data(0, self.instrument, semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)

    def test_cannot_set_nonexistent_semester(self):
        data = self.sci_data.copy()
        data['timerequest_set[0]semester'] = 'idontexist'
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)

    def test_cannot_set_an_instrument_that_is_not_part_of_the_call(self):
        instrument = mixer.blend(Instrument)
        data = {**self.sci_data.copy(), **generate_time_request_data(0, instrument, self.semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'The instrument IDs set for the time requests', status_code=400)

    def test_cannot_set_an_instrument_that_does_not_exist(self):
        data = self.sci_data.copy()
        data['timerequest_set[0]instrument'] += 10
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'object does not exist', status_code=400)

    def test_cannot_submit_an_application_before_the_call_opens(self):
        future_call = mixer.blend(
            Call, opens=timezone.now() + timedelta(days=7),
            closed=timezone.now() + timedelta(days=14), semester=self.semester,
            proposal_type=Call.SCI_PROPOSAL
        )
        data = self.sci_data.copy()
        data['call_id'] = future_call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'The call is not open', status_code=400)

    def test_cannot_submit_an_application_after_the_call_deadline(self):
        past_call = mixer.blend(
            Call, opens=timezone.now() - timedelta(days=14),
            closed=timezone.now() - timedelta(days=7), semester=self.semester,
            proposal_type=Call.SCI_PROPOSAL
        )
        data = self.sci_data.copy()
        data['call_id'] = past_call.id
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'The call is not open', status_code=400)

    def test_cannot_submit_an_application_for_a_call_that_doesnt_exist(self):
        data = self.sci_data.copy()
        data['call_id'] = 1000000000
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'object does not exist', status_code=400)

    def test_non_collab_application_cannot_set_tac_rank(self):
        data = self.sci_data.copy()
        data['tac_rank'] = 10
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'not allowed to set tac_rank', status_code=400)

    def test_collab_application_can_set_tac_rank(self):
        self.client.force_login(self.scicollab_admin)
        data = self.collab_data.copy()
        data['tac_rank'] = 10
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['tac_rank'], 10)

    def test_collab_application_can_set_zero_tac_rank(self):
        self.client.force_login(self.scicollab_admin)
        data = self.collab_data.copy()
        data['tac_rank'] = 0
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['tac_rank'], 0)

    def test_collab_application_requires_tac_rank_and_abstract(self):
        self.client.force_login(self.scicollab_admin)
        data = self.collab_data.copy()
        del data['tac_rank']
        del data['abstract']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('This field is required.', response.json().get('tac_rank'))
        self.assertIn('This field is required.', response.json().get('abstract'))

    def test_ddt_application_requires_pdf(self):
        data = self.ddt_data.copy()
        del data['pdf']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('A PDF is required for submission.', response.json().get('pdf'))

    def test_sci_application_requires_pdf_and_abstract(self):
        data = self.sci_data.copy()
        del data['abstract']
        del data['pdf']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('A PDF is required for submission.', response.json().get('pdf'))
        self.assertIn('This field is required.', response.json().get('abstract'))

    def test_can_save_draft_with_no_timerequests(self):
        data = {}
        for key, value in self.sci_data.items():
            if not key.startswith('timerequest'):
                data[key] = value
        data['status'] = ScienceApplication.DRAFT
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()['timerequest_set']), 0)

    def test_cannot_submit_application_with_no_timerequests(self):
        data = {}
        for key, value in self.sci_data.items():
            if not key.startswith('timerequest'):
                data[key] = value
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'You must provide at least one time request to submit', status_code=400)

    def test_collab_applications_cannot_submit_a_pdf(self):
        self.client.force_login(self.scicollab_admin)
        data = self.collab_data.copy()
        data['pdf'] = SimpleUploadedFile('s.pdf', b'ab')
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'collaboration proposals do not have pdfs', status_code=400)

    def test_cannot_set_random_statuses(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.ACCEPTED
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'Application status must be one', status_code=400)

    def test_number_of_words_in_abstract_is_limited(self):
        data = self.sci_data.copy()
        data['abstract'] = 'word ' * 600
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertContains(response, 'Abstract is limited to', status_code=400)


@patch('observation_portal.sciapplications.serializers.PdfFileReader', new=MockPDFFileReader)
class TestPostUpdateSciApp(DramatiqTestCase):
    def setUp(self):
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.instrument = mixer.blend(Instrument)
        self.sci_call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL, instruments=(self.instrument, )
        )
        self.ddt_call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.DDT_PROPOSAL, instruments=(self.instrument, )
        )
        self.sci_app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.sci_call
        )
        self.ddt_app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.ddt_call
        )
        data = {
            'title': fake.text(max_nb_chars=50),
            'status': ScienceApplication.DRAFT,
            'pi': fake.email(),
            'pi_first_name': fake.first_name(),
            'pi_last_name': fake.last_name(),
            'pi_institution': fake.company(),
            'abstract': fake.text(),
            'pdf': SimpleUploadedFile('sci.pdf', b'ab'),
            **generate_coinvestigator_data(0),
            **generate_time_request_data(0, self.instrument, self.semester)
        }
        self.sci_data = {
            'call_id': self.sci_call.id,
            **data.copy()
        }
        self.ddt_data = {
            'call_id': self.ddt_call.id,
            **data.copy()
        }

    def test_must_be_authenticated(self):
        self.client.logout()
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, self.sci_data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_update_non_draft(self):
        self.sci_app.status = ScienceApplication.SUBMITTED
        self.sci_app.save()
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, self.sci_data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 404)

    def test_can_update_draft(self):
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, self.sci_data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScienceApplication.objects.get(pk=self.sci_app.id).title, self.sci_data['title'])
        self.assertIsNone(ScienceApplication.objects.get(pk=self.sci_app.id).submitted)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 0)

    def test_can_submit_draft(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.SUBMITTED
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScienceApplication.objects.get(pk=self.sci_app.id).title, data['title'])
        self.assertTrue(ScienceApplication.objects.get(pk=self.sci_app.id).submitted)
        self.broker.join('default')
        self.worker.join()
        # Non DDT applications do not send the email to the user saying their application with be considered
        self.assertEqual(len(mail.outbox), 0)

    def test_can_update_set_of_timerequests(self):
        mixer.blend(TimeRequest, science_application=self.sci_app)
        mixer.blend(TimeRequest, science_application=self.sci_app)
        data = self.sci_data.copy()
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        time_request = TimeRequest.objects.filter(science_application=self.sci_app).first()
        self.assertEqual(TimeRequest.objects.filter(science_application=self.sci_app).count(), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(time_request.std_time, data['timerequest_set[0]std_time'])
        self.assertEqual(time_request.rr_time, data['timerequest_set[0]rr_time'])
        self.assertEqual(time_request.tc_time, data['timerequest_set[0]tc_time'])

    def test_cannot_submit_duplicate_timerequests(self):
        # Timerequests of the scieceapplication must be unique for instrument and semester
        data = self.sci_data.copy()
        # Add a second time request with the same instrument an semester
        data.update(generate_time_request_data(1, self.instrument, self.semester))
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertContains(response, 'cannot create more than one time request', status_code=400)

    def test_can_update_set_of_coinvestigators(self):
        mixer.blend(CoInvestigator, science_application=self.sci_app)
        mixer.blend(CoInvestigator, science_application=self.sci_app)
        mixer.blend(CoInvestigator, science_application=self.sci_app)
        data = self.sci_data.copy()
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data),
            content_type=MULTIPART_CONTENT
        )
        coinvestigator = CoInvestigator.objects.filter(science_application=self.sci_app).first()
        self.assertEqual(CoInvestigator.objects.filter(science_application=self.sci_app).count(), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(coinvestigator.email, data['coinvestigator_set[0]email'])
        self.assertEqual(coinvestigator.first_name, data['coinvestigator_set[0]first_name'])
        self.assertEqual(coinvestigator.last_name, data['coinvestigator_set[0]last_name'])
        self.assertEqual(coinvestigator.institution, data['coinvestigator_set[0]institution'])

    def test_submit_draft_that_has_pdf_saved_does_not_need_user_to_pass_in_pdf_field(self):
        data = self.sci_data.copy()
        uploaded_pdf = data['pdf']
        self.sci_app.pdf = uploaded_pdf
        self.sci_app.save()
        del data['pdf']
        data['status'] = ScienceApplication.SUBMITTED
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        submitted_sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(path.basename(submitted_sciapp.pdf.name), uploaded_pdf.name)

    def test_submitting_app_without_pdf_when_a_pdf_is_required_fails(self):
        data = self.sci_data.copy()
        data['status'] = ScienceApplication.SUBMITTED
        del data['pdf']
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertContains(response, 'A PDF is required for submission', status_code=400)

    def test_clearing_pdf_when_pdf_is_required_on_submission_fails(self):
        data = self.sci_data.copy()
        self.sci_app.pdf = data['pdf']
        self.sci_app.save()
        del data['pdf']
        data['clear_pdf'] = True
        data['status'] = ScienceApplication.SUBMITTED
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertContains(response, 'A PDF is required for submission', status_code=400)

    def test_leaving_out_a_pdf_doesnt_update_the_uploaded_pdf(self):
        uploaded_pdf = SimpleUploadedFile('app.pdf', b'123')
        self.sci_app.pdf = uploaded_pdf
        self.sci_app.save()
        self.assertEqual(path.basename(self.sci_app.pdf.name), uploaded_pdf.name)
        data = self.sci_data.copy()
        del data['pdf']
        data['title'] = 'Updated title'
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        updated_sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(path.basename(updated_sciapp.pdf.name), uploaded_pdf.name)
        self.assertEqual(updated_sciapp.title, data['title'])

    def test_setting_clear_pdf_clears_pdf(self):
        self.sci_app.pdf = SimpleUploadedFile('sci.pdf', b'ab')
        self.sci_app.save()
        self.assertTrue(self.sci_app.pdf)
        data = self.sci_data.copy()
        data['title'] = 'Updated title'
        del data['pdf']
        data['clear_pdf'] = True
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        updated_sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(updated_sciapp.pdf)
        self.assertEqual(updated_sciapp.title, data['title'])

    def test_cannot_set_both_pdf_and_clear_pdf(self):
        data = self.sci_data.copy()
        data['title'] = 'Updated title'
        data['clear_pdf'] = True
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertContains(response, 'Please either submit a new pdf or clear the existing pdf', status_code=400)

    def test_setting_new_pdf_updates_pdf(self):
        original_pdf = SimpleUploadedFile('first_upload.pdf', b'qwerty')
        self.sci_app.pdf = original_pdf
        self.sci_app.save()
        self.assertEqual(path.basename(self.sci_app.pdf.name), original_pdf.name)
        self.assertEqual(self.sci_app.pdf.size, original_pdf.size)
        data = self.sci_data.copy()
        data['title'] = 'Updated title'
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        updated_sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(path.basename(updated_sciapp.pdf.name), data['pdf'].name)
        self.assertEqual(updated_sciapp.pdf.size, data['pdf'].size)
        self.assertEqual(updated_sciapp.title, data['title'])

    def test_draft_ddt_does_not_send_notification_email(self):
        data = self.ddt_data.copy()
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.ddt_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(ScienceApplication.objects.get(id=self.ddt_app.id).submitted)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 0)

    def test_submitting_ddt_sends_email(self):
        data = self.ddt_data.copy()
        data['status'] = ScienceApplication.SUBMITTED
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.ddt_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ScienceApplication.objects.get(id=self.ddt_app.id).submitted)
        self.broker.join('default')
        self.worker.join()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(data['title'], str(mail.outbox[0].message()))
        self.assertIn(self.user.email, mail.outbox[0].to)
