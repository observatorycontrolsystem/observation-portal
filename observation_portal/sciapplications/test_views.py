from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from datetime import timedelta
from mixer.backend.django import mixer
from PyPDF2 import PdfFileMerger
from weasyprint import HTML
from unittest.mock import MagicMock, patch
from django_dramatiq.test import DramatiqTestCase

from observation_portal.proposals.models import Semester, ScienceCollaborationAllocation
from observation_portal.accounts.models import Profile
from observation_portal.sciapplications.models import ScienceApplication, Call, Instrument, TimeRequest, CoInvestigator
from observation_portal.sciapplications.forms import ScienceProposalAppForm, DDTProposalAppForm, KeyProjectAppForm
from observation_portal.sciapplications.forms import SciCollabAppForm
from observation_portal.accounts.test_utils import blend_user


class MockPDFFileReader:
    def __init__(self, bytesio):
        self.content = bytesio.getvalue()

    def getNumPages(self):
        return len(self.content)


class TestGetCreateSciApp(TestCase):
    def setUp(self):
        self.semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=1), end=timezone.now() + timedelta(days=365)
        )
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_no_call(self):
        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': 66})
        )
        self.assertEqual(response.status_code, 404)

    def test_get_sci_form(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.SCI_PROPOSAL
        )

        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': call.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['call'].id, call.id)
        self.assertIn('ScienceProposalAppForm', str(response.context['form'].__class__))

    def test_get_key_form(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.KEY_PROPOSAL
        )

        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': call.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['call'].id, call.id)
        self.assertIn('KeyProjectAppForm', str(response.context['form'].__class__))

    def test_get_ddt_form(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.DDT_PROPOSAL
        )

        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': call.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['call'].id, call.id)
        self.assertIn('DDTProposalAppForm', str(response.context['form'].__class__))

    def test_get_collab_form(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.COLLAB_PROPOSAL
        )
        mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': call.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['call'].id, call.id)
        self.assertIn('SciCollabAppForm', str(response.context['form'].__class__))

    def test_get_collab_form_normal_user(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            proposal_type=Call.COLLAB_PROPOSAL
        )
        response = self.client.get(
            reverse('sciapplications:create', kwargs={'call': call.id})
        )
        self.assertEqual(response.status_code, 404)


@patch('observation_portal.sciapplications.forms.PdfFileReader', new=MockPDFFileReader)
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
            'budget_details': 'test budget value',
            'abstract': 'test abstract value',
            'tac_rank': 1,
            'save': 'SAVE',
        }

        timerequest_data = {
            'timerequest_set-0-id': '',
            'timerequest_set-0-instrument': self.instrument.id,
            'timerequest_set-0-std_time': 30,
            'timerequest_set-0-rr_time': 1,
            'timerequest_set-0-tc_time': 5,

        }

        tr_management_data = {
            'timerequest_set-TOTAL_FORMS': 1,
            'timerequest_set-INITIAL_FORMS': 0,
            'timerequest_set-MIN_NUM_FORMS': 0,
            'timerequest_set-MAX_NUM_FORMS': 1000,
        }

        ci_data = {
            'coinvestigator_set-0-id': '',
            'coinvestigator_set-0-email': 'bilbo@baggins.com',
            'coinvestigator_set-0-first_name': 'Bilbo',
            'coinvestigator_set-0-last_name': 'Baggins',
            'coinvestigator_set-0-institution': 'lco',

        }

        ci_management_data = {
            'coinvestigator_set-TOTAL_FORMS': 1,
            'coinvestigator_set-INITIAL_FORMS': 0,
            'coinvestigator_set-MIN_NUM_FORMS': 0,
            'coinvestigator_set-MAX_NUM_FORMS': 1000,
        }

        self.sci_data = {k: data[k] for k in data if k in ScienceProposalAppForm.Meta.fields}
        self.sci_data.update(timerequest_data)
        self.sci_data.update(tr_management_data)
        self.sci_data.update(ci_data)
        self.sci_data.update(ci_management_data)
        self.key_data = {k: data[k] for k in data if k in KeyProjectAppForm.Meta.fields}
        self.key_data['call'] = self.key_call.id
        self.key_data.update(timerequest_data)
        self.key_data.update(tr_management_data)
        self.key_data.update(ci_data)
        self.key_data.update(ci_management_data)
        self.ddt_data = {k: data[k] for k in data if k in DDTProposalAppForm.Meta.fields}
        self.ddt_data['call'] = self.ddt_call.id
        self.ddt_data.update(timerequest_data)
        self.ddt_data.update(tr_management_data)
        self.ddt_data.update(ci_data)
        self.ddt_data.update(ci_management_data)
        self.collab_data = {k: data[k] for k in data if k in SciCollabAppForm.Meta.fields}
        self.collab_data['call'] = self.collab_call.id
        self.collab_data.update(timerequest_data)
        self.collab_data.update(tr_management_data)
        self.collab_data.update(ci_data)
        self.collab_data.update(ci_management_data)

    def test_post_sci_form(self):
        num_apps = ScienceApplication.objects.count()
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=self.sci_data,
            follow=True
        )
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.sci_data['title'])

    def test_post_key_form(self):
        num_apps = ScienceApplication.objects.count()
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.key_call.id}),
            data=self.key_data,
            follow=True
        )
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.sci_data['title'])

    def test_post_key_form_multiple_semesters(self):
        data = self.key_data.copy()
        other_semester = mixer.blend(
            Semester, start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data['timerequest_set-TOTAL_FORMS'] = 2
        data['timerequest_set-0-semester'] = self.semester.id

        data['timerequest_set-1-id'] = '',
        data['timerequest_set-1-semester'] = other_semester.id
        data['timerequest_set-1-instrument'] = self.instrument.id,
        data['timerequest_set-1-std_time'] = 30,
        data['timerequest_set-1-rr_time'] = 1,
        data['timerequest_set-1-tc_time'] = 5,
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.key_call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.user.scienceapplication_set.first().timerequest_set.filter(semester=self.semester).exists())
        self.assertTrue(self.user.scienceapplication_set.first().timerequest_set.filter(semester=other_semester).exists())

    def test_post_ddt_form(self):
        num_apps = ScienceApplication.objects.count()
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.ddt_call.id}),
            data=self.ddt_data,
            follow=True
        )
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.sci_data['title'])

    def test_post_collab_form(self):
        mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        num_apps = ScienceApplication.objects.count()
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.collab_call.id}),
            data=self.collab_data,
            follow=True
        )
        self.assertEqual(num_apps + 1, self.user.scienceapplication_set.count())
        self.assertContains(response, self.collab_data['title'])

    def test_normal_user_post_collab_form(self):
        num_apps = ScienceApplication.objects.count()
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.collab_call.id}),
            data=self.collab_data,
        )
        self.assertEqual(num_apps, self.user.scienceapplication_set.count())
        self.assertEqual(response.status_code, 404)

    def test_can_save_incomplete(self):
        data = self.sci_data.copy()
        data['status'] = 'DRAFT'
        del data['abstract']
        self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(self.user.scienceapplication_set.last().abstract, '')
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.DRAFT)

    def test_cannot_submit_incomplete(self):
        data = self.sci_data.copy()
        del data['abstract']
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertFalse(self.user.scienceapplication_set.all())
        self.assertContains(response, 'There was an error with your submission')

    def test_multiple_time_requests(self):
        data = self.sci_data.copy()
        data.update({
            'timerequest_set-1-id': '',
            'timerequest_set-1-instrument': self.instrument.id,
            'timerequest_set-1-std_time': 20,
            'timerequest_set-1-rr_time': 10,
            'timerequest_set-1-tc_time': 5,
            'timerequest_set-TOTAL_FORMS': 2,
        })
        self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(self.user.scienceapplication_set.last().timerequest_set.count(), 2)

    def test_multiple_coi(self):
        data = self.sci_data.copy()
        data.update({
            'coinvestigator_set-1-id': '',
            'coinvestigator_set-1-email': 'frodo@baggins.com',
            'coinvestigator_set-1-first_name': 'Frodo',
            'coinvestigator_set-1-last_name': 'Baggins',
            'coinvestigator_set-1-institution': 'lco',
            'coinvestigator_set-TOTAL_FORMS': 2,
        })
        self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(self.user.scienceapplication_set.last().coinvestigator_set.count(), 2)

    def test_can_post_own_email(self):
        data = self.sci_data.copy()
        data['pi'] = self.user.email
        self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(self.user.scienceapplication_set.last().pi, self.user.email)
        self.assertEqual(self.user.scienceapplication_set.last().status, ScienceApplication.SUBMITTED)

    def test_extra_pi_data_required(self):
        bad_data = self.sci_data.copy()
        del bad_data['pi_first_name']
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=bad_data,
            follow=True
        )
        self.assertFalse(self.user.scienceapplication_set.all())
        self.assertContains(response, 'There was an error with your submission')
        self.assertContains(response, 'Pi first name: This field is required')

    def test_can_leave_out_pi_in_draft(self):
        data = self.sci_data.copy()
        data['status'] = 'DRAFT'
        del data['pi']
        del data['pi_first_name']
        del data['pi_last_name']
        del data['pi_institution']
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.scienceapplication_set.last().pi, '')

    def test_cannot_leave_out_pi_in_submission(self):
        data = self.sci_data.copy()
        del data['pi']
        del data['pi_first_name']
        del data['pi_last_name']
        del data['pi_institution']
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertFalse(self.user.scienceapplication_set.all())
        self.assertContains(response, 'There was an error with your submission')
        self.assertContains(response, 'Pi: This field is required')

    def test_cannot_upload_silly_files(self):
        data = self.sci_data.copy()
        data['pdf'] = SimpleUploadedFile('notpdf.png', b'apngfile')
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'We can only accept PDF files')

    def test_submitting_ddt_sends_notification_email(self):
        data = self.ddt_data.copy()
        self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.ddt_call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(data['title'], str(mail.outbox[0].message()))
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_submitting_sets_submitted_date(self):
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=self.sci_data,
            follow=True
        )
        self.assertTrue(self.user.scienceapplication_set.first().submitted)
        self.assertContains(response, self.sci_data['title'])

    def test_pdf_has_too_many_pages(self):
        data = self.sci_data.copy()
        data['pdf'] = SimpleUploadedFile('s.pdf', b'this is way way way too long')
        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PDF file cannot exceed')

    def test_cannot_hack_in_other_semester(self):
        data = self.sci_data.copy()
        semester = mixer.blend(
            Semester, id='2000BC', start=timezone.now() + timedelta(days=20), end=timezone.now() + timedelta(days=60)
        )
        data['timerequest_set-0-semester'] = semester.id

        response = self.client.post(
            reverse('sciapplications:create', kwargs={'call': self.call.id}),
            data=data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.scienceapplication_set.first().timerequest_set.first().semester, self.semester)


class TestGetUpdateSciApp(TestCase):
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
        mixer.blend(Instrument, call=self.call)

    def test_can_view_draft(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:update', kwargs={'pk': app.id}))
        self.assertContains(response, app.title)

    def test_cannot_view_other_apps(self):
        other_user = blend_user()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=other_user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:update', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_submitted(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:update', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 404)


@patch('observation_portal.sciapplications.forms.PdfFileReader', new=MockPDFFileReader)
class TestPostUpdateSciApp(TestCase):
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
            'timerequest_set-TOTAL_FORMS': 1,
            'timerequest_set-INITIAL_FORMS': 1,
            'timerequest_set-MIN_NUM_FORMS': 1,
            'timerequest_set-MAX_NUM_FORMS': 1000,
            'timerequest_set-0-id': tr.id,
            'timerequest_set-0-instrument': self.instrument.id,
            'timerequest_set-0-std_time': tr.std_time,
            'timerequest_set-0-rr_time': tr.rr_time,
            'timerequest_set-0-tc_time': tr.tc_time,
            'coinvestigator_set-TOTAL_FORMS': 1,
            'coinvestigator_set-INITIAL_FORMS': 1,
            'coinvestigator_set-MIN_NUM_FORMS': 1,
            'coinvestigator_set-MAX_NUM_FORMS': 1000,
            'coinvestigator_set-0-id': coi.id,
            'coinvestigator_set-0-email': coi.email,
            'coinvestigator_set-0-first_name': coi.first_name,
            'coinvestigator_set-0-last_name': coi.last_name,
            'coinvestigator_set-0-institution': coi.institution
        }

    def test_can_update_draft(self):
        self.client.post(
            reverse('sciapplications:update', kwargs={'pk': self.app.id}),
            data=self.data,
            follow=True
        )
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
            'budget_details': 'test budget value',
            'abstract': 'test abstract value',
            'pdf': SimpleUploadedFile('sci.pdf', b'ab'),
            'save': 'SAVE',
        }
        data = {**data, **data_complete}
        self.client.post(
            reverse('sciapplications:update', kwargs={'pk': self.app.id}),
            data=data,
            follow=True
        )
        self.assertEqual(ScienceApplication.objects.get(pk=self.app.id).title, data['title'])
        self.assertTrue(ScienceApplication.objects.get(pk=self.app.id).submitted)


class TestSciAppIndex(TestCase):
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
        response = self.client.get(reverse('sciapplications:index'))
        self.assertEqual(response.status_code, 302)

    def test_index_no_applications(self):
        response = self.client.get(reverse('sciapplications:index'))
        self.assertContains(response, 'You have not started any proposals')

    def test_index(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:index'))
        self.assertContains(response, self.call.eligibility_short)
        self.assertContains(response, app.title)

    def test_normal_users_no_collab_calls(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.COLLAB_PROPOSAL,
            eligibility_short='For sci collab only'
        )
        response = self.client.get(reverse('sciapplications:index'))
        self.assertNotContains(response, call.eligibility_short)

    def test_collab_admin_collab_calls(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.COLLAB_PROPOSAL,
        )
        sca = mixer.blend(ScienceCollaborationAllocation, admin=self.user)
        response = self.client.get(reverse('sciapplications:index'))
        self.assertContains(response, sca.name + ' Proposals')

    def test_collab_admin_time_used(self):
        call = mixer.blend(
            Call, semester=self.semester,
            deadline=timezone.now() + timedelta(days=7),
            opens=timezone.now(),
            proposal_type=Call.COLLAB_PROPOSAL,
        )
        sca = mixer.blend(ScienceCollaborationAllocation, admin=self.user, one_meter_alloc=9)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=call
        )
        instrument = mixer.blend(Instrument, code='1M0-SCICAM-SBIG', telescope_class='1m0')
        tr = mixer.blend(TimeRequest, science_application=app, instrument=instrument, std_time=8)
        response = self.client.get(reverse('sciapplications:index'))
        self.assertContains(response, '{0}/{1}'.format(tr.std_time, sca.one_meter_alloc))


class TestSciAppDetail(TestCase):
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

    def test_can_view_details(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:detail', kwargs={'pk': app.id}))
        self.assertContains(response, app.title)

    def test_cannot_view_others_details(self):
        other_user = blend_user()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=other_user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:detail', kwargs={'pk': app.id}))
        self.assertEqual(response.status_code, 404)

    def test_staff_can_view_details(self):
        staff_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(staff_user)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:detail', kwargs={'pk': app.id}))
        self.assertContains(response, app.title)

    def test_pdf_view(self):
        # Just test the view here, actual pdf rendering is slow and loud
        PdfFileMerger.merge = MagicMock
        HTML.write_pdf = MagicMock
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:pdf', kwargs={'pk': app.id}))
        self.assertTrue(PdfFileMerger.merge.called)
        self.assertTrue(HTML.write_pdf.called)
        self.assertEqual(response.status_code, 200)

    def test_staff_can_view_pdf(self):
        PdfFileMerger.merge = MagicMock
        HTML.write_pdf = MagicMock
        staff_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(staff_user)
        self.client.force_login(staff_user)
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=self.user,
            call=self.call
        )
        response = self.client.get(reverse('sciapplications:pdf', kwargs={'pk': app.id}))
        self.assertTrue(PdfFileMerger.merge.called)
        self.assertTrue(HTML.write_pdf.called)
        self.assertEqual(response.status_code, 200)


class TestSciAppDelete(TestCase):
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
        response = self.client.post(
            reverse('sciapplications:delete', kwargs={'pk': app.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, app.title)
        self.assertFalse(ScienceApplication.objects.filter(pk=app.id).exists())

    def test_cannot_delete_non_draft(self):
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.SUBMITTED,
            submitter=self.user,
            call=self.call
        )
        response = self.client.post(
            reverse('sciapplications:delete', kwargs={'pk': app.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ScienceApplication.objects.filter(pk=app.id).exists())

    def test_cannot_delete_others(self):
        other_user = blend_user()
        app = mixer.blend(
            ScienceApplication,
            status=ScienceApplication.DRAFT,
            submitter=other_user,
            call=self.call
        )
        response = self.client.post(
            reverse('sciapplications:delete', kwargs={'pk': app.id}),
            data={'submit': 'Confirm'},
            follow=True
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ScienceApplication.objects.filter(pk=app.id).exists())
