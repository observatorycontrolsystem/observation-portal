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

from observation_portal.sciapplications.models import ScienceApplication, Call, CoInvestigator, Instrument, TimeRequest, ReviewPanel, ScienceApplicationReview, ScienceApplicationUserReview
from observation_portal.proposals.models import Semester, ScienceCollaborationAllocation, CollaborationAllocation
from observation_portal.accounts.test_utils import blend_user
from observation_portal.sciapplications.serializers import ScienceApplicationSerializer

fake = Faker()


def generate_time_request_data(index, instrument, semester):
    return {
        f'timerequest_set[{index}]instrument_types': [instrument.id],
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
        mixer.blend(TimeRequest, science_application=app, instrument_types=[instrument], std_time=8)
        response = self.client.get(reverse('api:scienceapplications-detail', kwargs={'pk': app.id}))
        self.assertEqual(response.json()['timerequest_set'][0]['std_time'], 8)
        self.assertIn('1 meter', response.json()['timerequest_set'][0]['telescope_names'])


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

    def test_filter_tags(self):
        app1 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call,
            tags=['transits', 'education']
        )
        app2 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call,
            tags=['transits']
        )
        mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call,
            tags=[]
        )
        # Get only apps with tag 'education'
        response = self.client.get(reverse('api:scienceapplications-list') + '?tags=education')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(app1.id, response.json()['results'][0]['id'])
        # Get only apps with tag 'transits'
        response = self.client.get(reverse('api:scienceapplications-list') + '?tags=transits')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)
        returned_app_ids = [app['id'] for app in response.json()['results']]
        self.assertTrue(app1.id in returned_app_ids)
        self.assertTrue(app2.id in returned_app_ids)
        # Get tags with either 'education' or 'transits'
        response = self.client.get(reverse('api:scienceapplications-list') + '?tags=transits,education')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)
        returned_app_ids = [app['id'] for app in response.json()['results']]
        self.assertTrue(app1.id in returned_app_ids)
        self.assertTrue(app2.id in returned_app_ids)
        # Don't filter for any tags
        response = self.client.get(reverse('api:scienceapplications-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 3)

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

    def test_submitting_sci_proposal_future_semester(self):
        semester = mixer.blend(
            Semester, id='2000BC', start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data = {**self.sci_data.copy(), **generate_time_request_data(0, self.instrument, semester)}
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)

    def test_cannot_set_noneligible_semester(self):
        semester = mixer.blend(
            Semester, id='2000BC', start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data = {**self.ddt_data.copy(), **generate_time_request_data(0, self.instrument, semester)}
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
        data['timerequest_set[0]instrument_types'] = [10]
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

    def test_create_sciapp_without_tags(self):
        data = self.sci_data.copy()
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertTrue(len(response.json()['tags']) == 0)

    def test_create_sciapp_with_tags(self):
        data = self.sci_data.copy()
        data['tags'] = ['planets', 'moon']
        response = self.client.post(reverse('api:scienceapplications-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(len(response.json()['tags']) == 2)
        self.assertTrue('planets' in response.json()['tags'])
        self.assertTrue('moon' in response.json()['tags'])


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

    def test_add_tags_to_sciapp(self):
        data = self.sci_data.copy()
        data['tags'] = ['planets', 'moon']
        sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        self.assertEqual(len(sciapp.tags), 0)
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        sciapp.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(sciapp.tags) == 2)
        self.assertTrue('planets' in sciapp.tags)
        self.assertTrue('moon' in sciapp.tags)
        self.assertIsNone(sciapp.submitted)

    def test_remove_tags_from_sciapp(self):
        sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        sciapp.tags = ['planets']
        sciapp.save()
        sciapp.refresh_from_db()
        self.assertEqual(sciapp.tags, ['planets'])
        data = self.sci_data.copy()
        # Leaving the tags field out when using multipart data on an update will clear out tags
        data.pop('tags', '')
        response = self.client.put(
            reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}),
            data=encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )
        self.assertEqual(response.status_code, 200)
        sciapp.refresh_from_db()
        self.assertEqual(sciapp.tags, [])
        self.assertIsNone(sciapp.submitted)

    def test_remove_tags_from_sciapp_using_json(self):
        sciapp = ScienceApplication.objects.get(pk=self.sci_app.id)
        sciapp.tags = ['planets', 'moon']
        sciapp.save()
        sciapp.refresh_from_db()
        self.assertTrue(len(sciapp.tags) == 2)
        self.assertTrue('planets' in sciapp.tags)
        self.assertTrue('moon' in sciapp.tags)
        data = {
            'title': fake.text(max_nb_chars=50),
            'status': ScienceApplication.DRAFT,
            'call_id': self.sci_call.id,
            'tags': []
        }
        response = self.client.put(reverse('api:scienceapplications-detail', kwargs={'pk': self.sci_app.id}), data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        sciapp.refresh_from_db()
        self.assertEqual(sciapp.tags, [])
        self.assertIsNone(sciapp.submitted)


@patch('observation_portal.sciapplications.serializers.PdfFileReader', new=MockPDFFileReader)
class TestCopySciApp(DramatiqTestCase):
    def setUp(self):
        self.upcoming_semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.old_semester = mixer.blend(
            Semester, start=timezone.now() - timedelta(days=365), end=timezone.now()
        )
        self.user = blend_user()
        self.client.force_login(self.user)
        self.instrument = mixer.blend(Instrument)
        self.old_sci_call = mixer.blend(
            Call, semester=self.old_semester,
            deadline=timezone.now() - timedelta(days=365),
            proposal_type=Call.SCI_PROPOSAL, instruments=(self.instrument, )
        )
        self.current_sci_call = mixer.blend(
            Call, semester=self.upcoming_semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL, instruments=(self.instrument, )
        )

        self.old_sci_app = mixer.blend(
            ScienceApplication,
            submitter=self.user,
            call=self.old_sci_call,
            title=fake.text(max_nb_chars=50),
            status=ScienceApplication.ACCEPTED,
            pi=fake.email(),
            pi_first_name=fake.first_name(),
            pi_last_name=fake.last_name(),
            pi_institution=fake.company(),
            abstract=fake.text(),
            pdf=SimpleUploadedFile('sci.pdf', b'ab'),
            **generate_coinvestigator_data(0),
            **generate_time_request_data(0, self.instrument, self.old_semester)
        )

    def test_copy_with_current_call(self):
        response = self.client.post(reverse('api:scienceapplications-copy', kwargs={'pk': self.old_sci_app.id}))

        science_applications = ScienceApplication.objects.filter(title=self.old_sci_app.title)
        sci_app_copy = science_applications[0]
        old_sci_app = science_applications[1]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(science_applications.count(), 2)
        self.assertEqual(sci_app_copy.status, ScienceApplication.DRAFT)
        self.assertNotEqual(sci_app_copy.pdf.name, old_sci_app.pdf.name)
        self.assertEqual(sci_app_copy.call.id, self.current_sci_call.id)
        self.assertEqual(sci_app_copy.call.semester.id, self.current_sci_call.semester.id)
        self.assertEqual(sci_app_copy.tac_rank, 0)
        self.assertEqual(sci_app_copy.tac_priority, 0)
        self.assertEqual(sci_app_copy.proposal, None)

        self.assertQuerysetEqual(sci_app_copy.coinvestigator_set.all(), old_sci_app.coinvestigator_set.all())
        self.assertQuerysetEqual(sci_app_copy.timerequest_set.all(), old_sci_app.timerequest_set.all())

    def test_copy_fails_no_current_call(self):
        self.current_sci_call.delete()

        response = self.client.post(reverse('api:scienceapplications-copy', kwargs={'pk': self.old_sci_app.id}))

        self.assertEqual(response.status_code, 400)
        self.assertIn('No open call at this time for proposal type SCI', response.json()['errors'][0])

    def test_copy_fails_not_correct_call(self):
        self.old_sci_app.call.proposal_type = Call.KEY_PROPOSAL
        self.old_sci_app.call.save()

        response = self.client.post(reverse('api:scienceapplications-copy', kwargs={'pk': self.old_sci_app.id}))

        self.assertEqual(response.status_code, 400)
        self.assertIn('No open call at this time for proposal type KEY', response.json()['errors'][0])


class TestReviewProcessAPI(APITestCase):

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

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse("api:scienceapplication-reviews-list"))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("api:scienceapplication-review-summary", kwargs={"pk": "2323"}))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("api:scienceapplication-my-review", kwargs={"pk": "2323"}))
        self.assertEqual(response.status_code, 403)

    def test_user_can_only_review_application_they_are_panelists_of(self):
        submitter = blend_user()

        app1 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        app2 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        panel1 = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )
        panel1.members.add(self.user)

        other_user = blend_user()

        panel2 = mixer.blend(
            ReviewPanel,
            name="panel 2",
        )
        panel2.members.add(other_user)

        app1_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app1,
            review_panel=panel1,
            primary_reviewer=self.user,
            secondary_reviewer=self.user,

        )

        app2_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app2,
            review_panel=panel2,
            primary_reviewer=other_user,
            secondary_reviewer=other_user,

        )

        response = self.client.get(reverse("api:scienceapplication-reviews-list"))
        self.assertEqual(response.json()["count"], 1)
        self.assertContains(response, app1_review.science_application.title)
        self.assertNotContains(response, app2_review.science_application.title)

    def test_users_my_review_is_theirs(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        other_user = blend_user()
        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        panel.members.set([self.user, other_user])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=self.user,
            secondary_reviewer=self.user,

        )

        my_review = mixer.blend(
            ScienceApplicationUserReview,
            science_application_review=app_review,
            reviewer=self.user,
            comments="yo"
        )

        mixer.blend(
            ScienceApplicationUserReview,
            science_application_review=app_review,
            reviewer=other_user,
            comments="not me"
        )

        response = self.client.get(reverse("api:scienceapplication-my-review", kwargs={"pk": app_review.pk}))
        self.assertEqual(response.json()["comments"], my_review.comments)

    def test_non_primary_or_secondary_can_not_summarize(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        other_user1 = blend_user()
        other_user2 = blend_user()
        panel.members.set([self.user, other_user1, other_user2])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=other_user1,
            secondary_reviewer=other_user2,

        )
        response = self.client.put(
            reverse("api:scienceapplication-review-summary", kwargs={"pk": app_review.pk}),
            data={"summary": "test"},
        )
        self.assertEqual(response.status_code, 403)

    def test_primary_can_summarize(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        other_user1 = blend_user()
        panel.members.set([self.user, other_user1])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=self.user,
            secondary_reviewer=other_user1,

        )
        response = self.client.put(
            reverse("api:scienceapplication-review-summary", kwargs={"pk": app_review.pk}),
            data={"summary": "test"},
        )
        self.assertEqual(response.json()["summary"], "test")

        app_review.refresh_from_db()
        self.assertEqual(app_review.summary, "test")

    def test_secondary_can_summarize(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        other_user1 = blend_user()
        panel.members.set([self.user, other_user1])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=other_user1,
            secondary_reviewer=self.user,

        )
        response = self.client.put(
            reverse("api:scienceapplication-review-summary", kwargs={"pk": app_review.pk}),
            data={"summary": "test"},
        )
        self.assertEqual(response.json()["summary"], "test")

        app_review.refresh_from_db()
        self.assertEqual(app_review.summary, "test")

    def test_members_of_admin_panels_can_view_all_proposals(self):
        submitter = blend_user()

        app1 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        app2 = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )
        other_user = blend_user()

        panel1 = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )
        panel1.members.add(other_user)


        panel2 = mixer.blend(
            ReviewPanel,
            name="panel 2",
        )
        panel2.members.add(other_user)

        admin_panel = mixer.blend(
            ReviewPanel,
            name="admin panel",
            is_admin=True,
        )
        admin_panel.members.add(self.user)

        app1_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app1,
            review_panel=panel1,
            primary_reviewer=other_user,
            secondary_reviewer=other_user,

        )

        app2_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app2,
            review_panel=panel2,
            primary_reviewer=other_user,
            secondary_reviewer=other_user,

        )

        response = self.client.get(reverse("api:scienceapplication-reviews-list"))
        self.assertEqual(response.json()["count"], 2)
        self.assertContains(response, app1_review.science_application.title)
        self.assertContains(response, app2_review.science_application.title)

    def test_admin_panel_memebers_can_summarize(self):
        submitter = blend_user()

        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=submitter,
            call=self.call
        )

        panel = mixer.blend(
            ReviewPanel,
            name="panel 1",
        )

        other_user1 = blend_user()
        panel.members.set([other_user1])

        app_review = mixer.blend(
            ScienceApplicationReview,
            science_application=app,
            review_panel=panel,
            primary_reviewer=other_user1,
            secondary_reviewer=other_user1,

        )

        admin_panel = mixer.blend(
            ReviewPanel,
            name="admin panel",
            is_admin=True,
        )
        admin_panel.members.add(self.user)

        response = self.client.put(
            reverse("api:scienceapplication-review-summary", kwargs={"pk": app_review.pk}),
            data={"summary": "test"},
        )
        self.assertEqual(response.json()["summary"], "test")

        app_review.refresh_from_db()
        self.assertEqual(app_review.summary, "test")
