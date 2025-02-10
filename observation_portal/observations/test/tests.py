from datetime import datetime, timedelta
from io import StringIO

from time_intervals.intervals import Intervals
from rest_framework.test import APITestCase
from django.utils import timezone
from mixer.backend.django import mixer
from dateutil.parser import parse
from django.urls import reverse
from django.core.cache import caches
from django.core.management import call_command
from rest_framework.authtoken.models import Token

from observation_portal.common.test_helpers import SetTimeMixin
from observation_portal.requestgroups.models import RequestGroup, Window, Location, Request
from observation_portal.observations.time_accounting import configuration_time_used, refund_configuration_status_time, refund_observation_time
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.proposals.models import Proposal, Membership, Semester, TimeAllocation
from observation_portal.common.test_helpers import create_simple_requestgroup, create_simple_configuration
from observation_portal.accounts.test_utils import blend_user
from observation_portal.observations import views
from observation_portal.observations import viewsets
import observation_portal.observations.signals.handlers  # noqa

from unittest.mock import patch
import copy

realtime = {
    "proposal": "auto_focus",
    "observation_type": "REAL_TIME",
    "name": "Test Real Time",
    "site": "tst",
    "enclosure": "domb",
    "telescope": "1m0a",
    "start": "2016-09-05T22:35:39Z",
    "end": "2016-09-05T23:35:40Z"
}

observation = {
    "request": {
        "configurations": [
            {
                "constraints": {
                    "max_airmass": 2.0,
                    "min_lunar_distance": 30.0,
                    "max_lunar_phase": 1.0,
                },
                "instrument_configs": [
                    {
                        "optical_elements": {
                            "filter": "air"
                        },
                        "exposure_time": 370.0,
                        "exposure_count": 1,
                        "rotator_mode": "",
                        "extra_params": {}
                    }
                ],
                "acquisition_config": {
                    "mode": "OFF",
                    "extra_params": {}
                },
                "guiding_config": {
                    "mode": "OFF",
                    "optional": False,
                    "optical_elements": {},
                    "exposure_time": 10.0,
                    "extra_params": {}
                },
                "target": {
                    "parallax": 0.0,
                    "proper_motion_ra": 0.0,
                    "ra": 83.3833402357991,
                    "type": "ICRS",
                    "epoch": 2000.0,
                    "name": "auto_focus",
                    "dec": -33.0,
                    "proper_motion_dec": 0.0
                },
                "instrument_type": "1M0-SCICAM-SBIG",
                "type": "EXPOSE",
                "extra_params": {},
            }
        ],
        "observation_note": "Submitted to scheduler.",
        "state": "PENDING",
        "acceptability_threshold": 90.0
    },
    "proposal": "auto_focus",
    "observation_type": "NORMAL",
    "name": "Focus request.",
    "site": "tst",
    "enclosure": "domb",
    "telescope": "1m0a",
    "start": "2016-09-05T22:35:39Z",
    "end": "2016-09-05T23:35:40Z"
}


class TestPostScheduleApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, direct_submission=True)
        self.user = blend_user(user_params={'is_admin': True, 'is_superuser': True, 'is_staff': True})
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )

        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.observation = copy.deepcopy(observation)
        self.observation['proposal'] = self.proposal.id

    def test_post_observation_user_not_logged_in(self):
        other_user = blend_user()
        self.client.force_login(other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 403)

    def test_post_observation_user_not_on_proposal(self):
        other_user = blend_user(user_params={'is_staff': True})
        self.client.force_login(other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('do not belong to the proposal', str(response.content))

    def test_post_observation_authenticated(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], self.observation['name'])

    def test_non_staff_direct_user_on_own_direct_proposal(self):
        other_user = blend_user()
        mixer.blend(Membership, user=other_user, proposal=self.proposal)
        self.client.force_login(other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], self.observation['name'])

    def test_non_staff_direct_user_submits_to_another_non_direct_proposal_of_theirs_fails(self):
        other_user = blend_user()
        mixer.blend(Membership, user=other_user, proposal=self.proposal)
        self.proposal.direct_submission = False
        self.proposal.save()
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, user=other_user, proposal=other_proposal)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_non_staff_direct_user_submits_to_direct_proposal_thats_not_theirs_fails(self):
        other_user = blend_user()
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, proposal=other_proposal, user=other_user)
        self.client.force_login(other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('do not belong to the proposal', str(response.content))
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_post_multiple_observations_succeeds(self):
        observations = [self.observation, self.observation, self.observation]
        response = self.client.post(reverse('api:schedule-list'), data=observations)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(Observation.objects.all()), 3)
        self.assertEqual(len(RequestGroup.objects.all()), 3)

    def test_post_observation_creates_config_status(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        observation = Observation.objects.get(id=response.json()['id'])
        config_status = ConfigurationStatus.objects.get(observation=observation)
        self.assertEqual(response.json()['request']['configurations'][0]['configuration_status'], config_status.id)

    def test_post_observation_requires_proposal(self):
        bad_observation = copy.deepcopy(self.observation)
        del bad_observation['proposal']
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('proposal', response.json())
        self.assertIn('field is required', str(response.content))

    def test_post_observation_requires_real_proposal(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = 'FAKE_PROPOSAL'
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('proposal', response.json())
        self.assertIn('does not exist', str(response.content))

    def test_post_observation_requires_proposal_with_direct_submission(self):
        self.proposal.direct_submission = False
        self.proposal.save()
        bad_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is not allowed to submit observations directly', str(response.content))

    def test_post_observation_validates_site(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['site'] = 'fake'
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('site', response.json())

    def test_post_observation_time_in_past_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['start'] = "2014-09-05T22:15:39Z"
        bad_observation['end'] = "2014-09-05T22:35:39Z"
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('end', response.json())
        self.assertIn('must be in the future', str(response.content))

    def test_post_observation_end_before_start_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['end'] = "2016-09-05T21:35:40Z"
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('end time must be after start time', str(response.content).lower())

    def test_post_observation_invalid_instrument_type_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['request']['configurations'][0]['instrument_type'] = '1M0-FAKE-INSTRUMENT'
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid instrument type', str(response.content).lower())

    def test_post_observation_instrument_name_accepted(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['instrument_name'] = 'xx03'
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)

    def test_post_observation_works_with_priority(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        obs_json = response.json()
        self.assertEqual(obs_json['priority'], 10)

        observation = copy.deepcopy(self.observation)
        observation['priority'] = 39
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)
        obs_json = response.json()
        self.assertEqual(obs_json['priority'], 39)

    def test_post_observation_invalid_instrument_name_for_instrument_type(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['request']['configurations'][0]['instrument_name'] = 'fake01'
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is not an available', str(response.content))

    def test_post_observation_no_instrument_name_sets_default_for_instrument_type(self):
        observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        obs_json = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(obs_json['request']['configurations'][0]['instrument_name'], 'xx03')

    def test_post_observation_invalid_instrument_type_for_site_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['site'] = 'lco'
        bad_observation['request']['configurations'][0]['instrument_type'] = '1M0-SCICAM-SBIG'
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is not available at', str(response.content))

    def test_post_observation_invalid_guide_camera_name_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        # ef01 is only on doma, this observation is on domb so it should fail to validate ef01
        bad_observation['request']['configurations'][0]['guide_camera_name'] = 'ak03'
        bad_observation['request']['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        bad_observation['request']['configurations'][0]['guiding_config']['mode'] = 'ON'
        bad_observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        bad_observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
        del bad_observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid guide camera', str(response.content))

    def test_post_observation_good_guide_camera_name_accepted(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['guide_camera_name'] = 'ak02'
        observation['request']['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        observation['request']['configurations'][0]['guiding_config']['mode'] = 'ON'
        observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
        observation['request']['configurations'][0]['instrument_configs'][0]['mode'] = '1m0_nres_1'
        del observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)

    def test_post_observation_no_guide_camera_sets_default(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        observation['request']['configurations'][0]['guiding_config']['mode'] = 'ON'
        observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
        observation['request']['configurations'][0]['instrument_configs'][0]['mode'] = '1m0_nres_1'
        del observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        obs_json = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(obs_json['request']['configurations'][0]['guide_camera_name'], 'ak02')

    def test_self_guiding_with_no_guide_camera_set_sets_same_instrument_for_guide_camera(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['guiding_config']['mode'] = 'ON'
        observation['request']['configurations'][0]['extra_params']['self_guide'] = True
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        obs_json = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            obs_json['request']['configurations'][0]['instrument_name'],
            obs_json['request']['configurations'][0]['guide_camera_name']
        )
        self.assertIs(obs_json['request']['configurations'][0]['extra_params']['self_guide'], observation['request']['configurations'][0]['extra_params']['self_guide'])

    def test_post_observation_hour_angle_missing_required_fields(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['request']['configurations'][0]['target']['type'] = 'HOUR_ANGLE'
        bad_observation['request']['configurations'][0]['target']['ha'] = 9.45
        del bad_observation['request']['configurations'][0]['target']['ra']
        del bad_observation['request']['configurations'][0]['target']['dec']

        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('dec', str(response.content))

    def test_post_observation_hour_angle_target_of_zero_succeeds(self):
        good_observation = copy.deepcopy(self.observation)
        good_observation['request']['configurations'][0]['target']['type'] = 'HOUR_ANGLE'
        good_observation['request']['configurations'][0]['target']['hour_angle'] = 0
        del good_observation['request']['configurations'][0]['target']['ra']
        response = self.client.post(reverse('api:schedule-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)

    def test_delete_observation_leaves_request(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        obj_json = response.json()
        observation = Observation.objects.get(pk=obj_json['id'])
        observation.state = 'CANCELED'
        observation.save()
        Observation.delete_old_observations(datetime(2099, 1, 1, tzinfo=timezone.utc))
        request = Request.objects.get(id=obj_json['request']['id'])
        self.assertEqual(request.id, obj_json['request']['id'])
        with self.assertRaises(Observation.DoesNotExist):
            observation = Observation.objects.get(pk=obj_json['id'])

    def test_cant_delete_observation_with_started_configuration_statuses(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        obj_json = response.json()
        observation = Observation.objects.get(pk=obj_json['id'])
        observation.state = 'CANCELED'
        observation.save()
        configuration_status = observation.configuration_statuses.all()[0]
        configuration_status.state = 'ATTEMPTED'
        configuration_status.save()
        Observation.delete_old_observations(datetime(2099, 1, 1, tzinfo=timezone.utc))
        observation = Observation.objects.get(pk=obj_json['id'])
        self.assertEqual(observation.id, obj_json['id'])


class TestPostScheduleMultiConfigApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, direct_submission=True)
        self.user = blend_user(user_params={'is_admin': True, 'is_superuser': True, 'is_staff': True})
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )

        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.observation = copy.deepcopy(observation)
        self.observation['proposal'] = self.proposal.id
        # Add two more configurations, and modify their properties in tests
        self.observation['request']['configurations'].append(copy.deepcopy(
            self.observation['request']['configurations'][0]
        ))
        self.observation['request']['configurations'].append(copy.deepcopy(
            self.observation['request']['configurations'][0]
        ))
        self.observation['request']['configurations'][2]['instrument_type'] = '1M0-NRES-SCICAM'
        self.observation['request']['configurations'][2]['guiding_config']['mode'] = 'ON'
        self.observation['request']['configurations'][2]['acquisition_config']['mode'] = 'WCS'
        self.observation['request']['configurations'][2]['type'] = 'NRES_SPECTRUM'
        self.observation['request']['configurations'][2]['instrument_configs'][0]['mode'] = '1m0_nres_1'
        del self.observation['request']['configurations'][2]['instrument_configs'][0]['optical_elements']['filter']

    def test_post_observation_multiple_configurations_accepted(self):
        observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)
        obs_json = response.json()
        # verify instruments were set correctly
        self.assertEqual(obs_json['request']['configurations'][0]['instrument_name'], 'xx03')
        self.assertEqual(obs_json['request']['configurations'][1]['instrument_name'], 'xx03')
        self.assertEqual(obs_json['request']['configurations'][2]['instrument_name'], 'nres02')
        self.assertEqual(obs_json['request']['configurations'][0]['instrument_type'], '1M0-SCICAM-SBIG')
        self.assertEqual(obs_json['request']['configurations'][1]['instrument_type'], '1M0-SCICAM-SBIG')
        self.assertEqual(obs_json['request']['configurations'][2]['instrument_type'], '1M0-NRES-SCICAM')

    def test_post_observation_multiple_configurations_with_instrument_names(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['instrument_name'] = 'xx03'
        observation['request']['configurations'][1]['instrument_name'] = 'xx03'
        observation['request']['configurations'][2]['instrument_name'] = 'nres02'

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)

    def test_post_observation_multiple_configurations_with_bad_instrument_name_rejected(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['request']['configurations'][1]['instrument_name'] = 'nres03'
        bad_observation['request']['configurations'][2]['instrument_name'] = 'xx03'

        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)


class TestRealTimeApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, id='auto_focus', direct_submission=True, active=True)
        self.user = blend_user(
            user_params={'is_admin': True, 'is_superuser': True, 'is_staff': True},
            profile_params={'staff_view': True})
        Token.objects.get_or_create(user=self.user)
        self.nonstaff_user = blend_user(user_params={'is_admin': False, 'is_superuser': False, 'is_staff': False})
        Token.objects.get_or_create(user=self.nonstaff_user)
        self.client.force_login(self.nonstaff_user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.ta = mixer.blend(TimeAllocation, proposal=self.proposal, semester=self.semester, realtime_allocation=10.0, instrument_types=['1M0-SCICAM-SBIG',])
        self.membership = mixer.blend(Membership, user=self.nonstaff_user, proposal=self.proposal)
        self.observation = copy.deepcopy(realtime)
        self.observation['proposal'] = self.proposal.id

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_observation_succeeds_with_nonstaff_user(self, create_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['submitter'], self.nonstaff_user.username)
        self.assertEqual(response.json()['observation_type'], self.observation['observation_type'])
        self.assertEqual(response.json()['name'], self.observation['name'])
        # Make sure time is debitted on creation
        self.ta.refresh_from_db()
        time_used = (parse(self.observation['end']) - parse(self.observation['start'])).total_seconds() / 3600.0
        self.assertEqual(time_used, self.ta.realtime_time_used)

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_observation_succeeds_with_staff_user(self, create_downtime):
        self.client.force_login(self.user)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['submitter'], self.user.username)
        self.assertEqual(response.json()['observation_type'], self.observation['observation_type'])
        self.assertEqual(response.json()['name'], self.observation['name'])

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_observation_fails_if_downtime_creation_fails(self, create_downtime):
        create_downtime.side_effect = Exception("Failed to create downtime")
        self.client.force_login(self.user)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Failed to create downtime for Realtime observation', str(response.content))
        # Make sure no observations were created
        self.assertEqual(Observation.objects.all().count(), 0)

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    @patch('observation_portal.common.downtimedb.DowntimeDB.delete_downtime_interval')
    def test_delete_realtime_observation_succeeds(self, create_downtime, delete_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        # Make sure time is debitted on creation
        self.ta.refresh_from_db()
        time_used = (parse(self.observation['end']) - parse(self.observation['start'])).total_seconds() / 3600.0
        self.assertEqual(time_used, self.ta.realtime_time_used)

        observation_id = response.json()['id']
        Observation.objects.get(id=observation_id)
        request_group_id = response.json()['request_group_id']
        RequestGroup.objects.get(id=request_group_id)
        response = self.client.delete(reverse('api:realtime-detail', args=(observation_id,)))
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(Observation.DoesNotExist):
            Observation.objects.get(id=observation_id)
        with self.assertRaises(RequestGroup.DoesNotExist):
            RequestGroup.objects.get(id=request_group_id)
        # Now make sure time is credited back on deletion
        self.ta.refresh_from_db()
        self.assertEqual(0.0, self.ta.realtime_time_used)

    @patch('observation_portal.common.downtimedb.DowntimeDB.delete_downtime_interval')
    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_delete_someone_elses_observation_fails(self, create_downtime, delete_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        observation_id = response.json()['id']

        # Make another non-staff user and show they cannot delete it
        someone_else = blend_user(user_params={'is_admin': False, 'is_superuser': False, 'is_staff': False})
        self.client.force_login(someone_else)
        response = self.client.delete(reverse('api:realtime-detail', args=(observation_id,)))
        self.assertEqual(response.status_code, 404)

    @patch('observation_portal.common.downtimedb.DowntimeDB.delete_downtime_interval')
    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_delete_someone_elses_observation_succeeds_as_staff(self, create_downtime, delete_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        observation_id = response.json()['id']

        self.client.force_login(self.user)
        response = self.client.delete(reverse('api:realtime-detail', args=(observation_id,)))
        self.assertEqual(response.status_code, 204)

    @patch('observation_portal.common.downtimedb.DowntimeDB.delete_downtime_interval')
    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_delete_observation_fails_if_downtime_deletion_fails(self, create_downtime, delete_downtime):
        delete_downtime.side_effect = Exception("Failed to delete downtime")
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        observation_id = response.json()['id']

        self.client.force_login(self.user)
        response = self.client.delete(reverse('api:realtime-detail', args=(observation_id,)))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Failed to delete downtime associated with Realtime observation', str(response.content))
        # Make sure observation still exists
        self.assertEqual(Observation.objects.filter(id=observation_id).count(), 1)

    def test_delete_nonexistent_observation(self):
        response = self.client.delete(reverse('api:realtime-detail', args=(12345,)))
        self.assertEqual(response.status_code, 404)

    def test_post_realtime_user_not_on_proposal(self):
        proposal = mixer.blend(Proposal, direct_submission=True, active=True)
        mixer.blend(Membership, user=self.user, proposal=proposal)
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = proposal.id
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is not a member of proposal', str(response.content))

    def test_post_realtime_proposal_not_active(self):
        inactive_proposal = mixer.blend(Proposal, direct_submission=True, active=False)
        mixer.blend(Membership, user=self.nonstaff_user, proposal=inactive_proposal)
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = inactive_proposal.id
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is not active', str(response.content))

    def test_post_realtime_proposal_no_time_allocation(self):
        test_proposal = mixer.blend(Proposal, direct_submission=True, active=True)
        mixer.blend(Membership, user=self.nonstaff_user, proposal=test_proposal)
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = test_proposal.id
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Not enough realtime time allocation available on proposal', str(response.content))

    def test_post_realtime_proposal_not_enough_time_allocation(self):
        test_proposal = mixer.blend(Proposal, direct_submission=True, active=True)
        mixer.blend(Membership, user=self.nonstaff_user, proposal=test_proposal)
        mixer.blend(TimeAllocation, proposal=test_proposal, semester=self.semester, realtime_allocation=0.5, instrument_types=['1M0-SCICAM-SBIG',])
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = test_proposal.id
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn(f'Not enough realtime time allocation available on proposal {test_proposal.id}: 0.5 hours available', str(response.content))

    def test_post_realtime_proposal_does_not_exist(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['proposal'] = 'fakeProposal'
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Proposal fakeProposal does not exist', str(response.content))

    def test_post_telescope_does_not_exist(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['site'] = 'lco'
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('No instruments found at lco.domb.1m0a', str(response.content))

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_observation_has_configuration_status_created(self, create_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertIn('configuration_status_id', response.json())
        observation = Observation.objects.first().as_dict()
        self.assertEqual(observation['request']['configurations'][0]['configuration_status'],
                         response.json()['configuration_status_id'])

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_update_configuration_state_succeeds(self, create_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        configuration_status_id = response.json()['configuration_status_id']
        configuration_status = ConfigurationStatus.objects.first()
        self.assertEqual(configuration_status.id, configuration_status_id)
        self.assertEqual(configuration_status.state, 'PENDING')
        update_data = {'state': 'ATTEMPTED'}
        self.client.force_login(self.user)
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status_id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'ATTEMPTED')

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_update_configuration_state_completed_makes_observation_complete(self, create_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        configuration_status_id = response.json()['configuration_status_id']
        update_data = {'state': 'COMPLETED'}
        self.client.force_login(self.user)
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status_id,)), update_data)
        observation = Observation.objects.first()
        self.assertEqual(observation.state, 'COMPLETED')

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_observation_has_configurations(self, create_downtime):
        response = self.client.post(reverse('api:realtime-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        observation = Observation.objects.first().as_dict()

        response = self.client.get(reverse('api:schedule-list'))
        self.assertEqual(response.json()['count'], 1)
        test_obs1 = response.json()['results'][0]
        self.assertEqual(observation['id'], test_obs1['id'])
        self.assertEqual(observation['request']['configurations'], test_obs1['request']['configurations'])

        response = self.client.get(reverse('api:observations-list'))
        self.assertEqual(response.json()['count'], 1)
        test_obs2 = response.json()['results'][0]
        self.assertEqual(observation['id'], test_obs2['id'])
        self.assertEqual(observation['request']['configurations'], test_obs2['request']['configurations'])

    def test_post_realtime_rejected_during_daytime(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['start'] = "2016-09-05T12:35:39Z"
        bad_observation['end'] = "2016-09-05T13:35:39Z"
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The desired interval', str(response.content))

    def test_post_realtime_rejected_during_daytime_overlapping(self):
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['start'] = "2016-09-05T16:35:39Z"
        bad_observation['end'] = "2016-09-05T18:35:39Z"
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The desired interval', str(response.content))

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_post_realtime_rejected_due_to_downtime_during_interval(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-05T23:00:00Z',
                                       'end': '2016-09-05T23:10:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'instrument_type': '',
                                       'reason': 'Whatever'},
                                      ]
        bad_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The desired interval', str(response.content))

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_accepted_with_nonoverlapping_downtime(self, create_downtime, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-05T21:00:00Z',
                                       'end': '2016-09-05T22:10:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'instrument_type': '',
                                       'reason': 'Whatever'},
                                      ]
        good_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_rejected_if_overlapping_users_other_sessions(self, create_downtime):
        # Create one realtime observation
        good_observation = copy.deepcopy(self.observation)
        good_observation['enclosure'] = 'doma'
        good_observation['start'] = "2016-09-05T23:00:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)
        # Then attempt to create another realtime observation that would overlap but on a different resource
        bad_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn("overlaps an existing interval for user", str(response.content))

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_rejected_if_overlapping_in_progress_observations(self, create_downtime):
        # First create an in progress observation during the same time as the realtime session
        mixer.blend(Observation, state='IN_PROGRESS', start=datetime(2016, 9, 1, 0, tzinfo=timezone.utc),
                    end=datetime(2016, 9, 1, 1, tzinfo=timezone.utc), site='tst', enclosure='domb', telescope='1m0a')
        # Then show that the realtime session fails to book
        bad_observation = copy.deepcopy(self.observation)
        bad_observation['start'] = "2016-09-01T00:15:00Z"
        bad_observation['end'] = "2016-09-01T01:15:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn("There is currently an observation in progress on tst.domb.1m0a", str(response.content))
        # overlapping fails to book again
        bad_observation['start'] = "2016-09-01T00:15:00Z"
        bad_observation['end'] = "2016-09-01T00:45:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn("There is currently an observation in progress on tst.domb.1m0a", str(response.content))
        # Non overlapping succeeds at booking
        good_observation = copy.deepcopy(self.observation)
        good_observation['start'] = "2016-09-01T01:15:00Z"
        good_observation['end'] = "2016-09-01T01:30:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_rejected_if_overlapping_important_scheduled_observations(self, create_downtime):
        # First schedule an important observation during the same time as the realtime session
        requestgroup = create_simple_requestgroup(
            self.nonstaff_user, self.proposal, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.TIME_CRITICAL
        requestgroup.save()
        mixer.blend(Observation, request=requestgroup.requests.first(), state='PENDING',
                    start=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                    end=datetime(2016, 9, 5, 23, tzinfo=timezone.utc),
                    site='tst', enclosure='domb', telescope='1m0a')
        # Then show that the realtime session fails to book
        bad_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:realtime-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn("This session overlaps a currently scheduled high priority observation", str(response.content))
        # Non overlapping succeeds at booking
        good_observation = copy.deepcopy(self.observation)
        good_observation['start'] = "2016-09-05T23:15:00Z"
        good_observation['end'] = "2016-09-05T23:30:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_post_realtime_succeeds_if_overlapping_normal_scheduled_observations(self, create_downtime):
        # First create an in progress observation during the same time as the realtime session
        requestgroup = create_simple_requestgroup(
            self.nonstaff_user, self.proposal, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.NORMAL
        requestgroup.save()
        mixer.blend(Observation, request=requestgroup.requests.first(), state='IN_PROGRESS',
                    start=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                    end=datetime(2016, 9, 5, 23, tzinfo=timezone.utc),
                    site='tst', enclosure='domb', telescope='1m0a')
        good_observation = copy.deepcopy(self.observation)
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)

    def test_realtime_availability_is_limited_by_proposal_time_allocation(self):
        response = self.client.get(reverse('api:realtime-availability'))
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertTrue(availability)
        for key in availability.keys():
            # The default proposal only has 1m0-sbig realtime time
            self.assertIn('1m0a', key)

        # Now remove the proposal time allocation and see that there is no availability
        self.ta.delete()
        response = self.client.get(reverse('api:realtime-availability'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {})

    def _convert_availability_to_intervals_helper(self, interval_list):
        intervals = []
        for interval in interval_list:
            intervals.append((parse(interval[0]), parse(interval[1])))
        return Intervals(intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_realtime_availability_filters_out_existing_observation_blocks(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-05T21:00:00Z',
                                       'end': '2016-09-05T22:10:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'instrument_type': '',
                                       'reason': 'Whatever'},
                                     ]
        response = self.client.get(reverse('api:realtime-availability') + '?telescope=1m0a.domb.tst')
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertContains(response, '1m0a.domb.tst')
        available_intervals = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals.is_empty())
        # Check that the downtime interval is not within the available intervals
        blocked_interval = Intervals([(datetime(2016, 9, 5, 21, 5, tzinfo=timezone.utc), datetime(2016, 9, 5, 22, tzinfo=timezone.utc))])
        self.assertTrue(available_intervals.intersect([blocked_interval]).is_empty())
        # Make sure the same times the next day are available so we know using the downtime was real
        free_interval = Intervals([(datetime(2016, 9, 6, 21, 5, tzinfo=timezone.utc), datetime(2016, 9, 6, 22, tzinfo=timezone.utc))])
        self.assertFalse(available_intervals.intersect([free_interval]).is_empty())

    @patch('observation_portal.common.downtimedb.DowntimeDB.create_downtime_interval')
    def test_realtime_availability_filters_out_times_user_has_other_realtime_sessions(self, create_downtime):
        # Create one realtime observation on 1m0a.tst.doma
        good_observation = copy.deepcopy(self.observation)
        good_observation['enclosure'] = 'doma'
        good_observation['start'] = "2016-09-05T23:00:00Z"
        good_observation['end'] = "2016-09-05T23:30:00Z"
        response = self.client.post(reverse('api:realtime-list'), data=good_observation)
        self.assertEqual(response.status_code, 201)
        # Now get availability intervals for 1m0a.tst.domb and make sure that time booked on doma is not available
        response = self.client.get(reverse('api:realtime-availability') + '?telescope=1m0a.domb.tst')
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertContains(response, '1m0a.domb.tst')
        available_intervals = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals.is_empty())
        # Check that the overlapping interval is not within the available intervals
        blocked_interval = Intervals([(datetime(2016, 9, 5, 23, 0, tzinfo=timezone.utc), datetime(2016, 9, 5, 23, 30, tzinfo=timezone.utc))])
        self.assertTrue(available_intervals.intersect([blocked_interval]).is_empty())
        # Now get the availability intervals again but for a different user with no realtime booking to show their free
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:realtime-availability') + '?telescope=1m0a.domb.tst')
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        available_intervals = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals.intersect([blocked_interval]).is_empty())

    def test_realtime_availability_filters_out_times_overlapping_with_in_progress_observations(self):
        # First create two in progress observations on different resources during the time range
        observation_a = mixer.blend(Observation, state='IN_PROGRESS',
                            start=datetime(2016, 9, 5, 21, tzinfo=timezone.utc),
                            end=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                            site='tst', enclosure='doma', telescope='1m0a')
        observation_b = mixer.blend(Observation, state='IN_PROGRESS',
                                  start=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                                  end=datetime(2016, 9, 6, 0, tzinfo=timezone.utc),
                                  site='tst', enclosure='domb', telescope='1m0a')

        # Now get availability intervals and make sure the in progress times are not available
        response = self.client.get(reverse('api:realtime-availability'))
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertContains(response, '1m0a.doma.tst')
        self.assertContains(response, '1m0a.domb.tst')
        available_intervals_a = self._convert_availability_to_intervals_helper(availability['1m0a.doma.tst'])
        available_intervals_b = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals_a.is_empty())
        self.assertFalse(available_intervals_b.is_empty())
        # Check that the in progress observation intervals are not within the available intervals
        blocked_interval_a = Intervals([(observation_a.start, observation_a.end)])
        self.assertTrue(available_intervals_a.intersect([blocked_interval_a]).is_empty())
        blocked_interval_b = Intervals([(observation_b.start, observation_b.end)])
        self.assertTrue(available_intervals_b.intersect([blocked_interval_b]).is_empty())
        # Check times before and after the blocked intervals
        free_intervals_a = Intervals([(datetime(2016, 9, 5, 20, 45, tzinfo=timezone.utc),
                                     datetime(2016, 9, 5, 20, 59, tzinfo=timezone.utc)),
                                    (datetime(2016, 9, 5, 22, 1, tzinfo=timezone.utc),
                                     datetime(2016, 9, 5, 22, 15, tzinfo=timezone.utc))])
        self.assertEquals(available_intervals_a.intersect([free_intervals_a]), free_intervals_a)
        free_intervals_b = Intervals([(datetime(2016, 9, 5, 21, tzinfo=timezone.utc),
                                     datetime(2016, 9, 5, 21, 59, tzinfo=timezone.utc)),
                                    (datetime(2016, 9, 6, 0, 1, tzinfo=timezone.utc),
                                     datetime(2016, 9, 6, 0, 15, tzinfo=timezone.utc))])
        self.assertEquals(available_intervals_b.intersect([free_intervals_b]), free_intervals_b)

    def test_realtime_availability_filters_out_times_overlapping_with_future_important_observations(self):
       # First schedule an important observation during the time range
        requestgroup = create_simple_requestgroup(
            self.nonstaff_user, self.proposal, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.TIME_CRITICAL
        requestgroup.save()
        tc_observation = mixer.blend(Observation, request=requestgroup.requests.first(), state='PENDING',
                                     start=datetime(2016, 9, 5, 21, tzinfo=timezone.utc),
                                     end=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                                     site='tst', enclosure='domb', telescope='1m0a')
        # Now get availability intervals for 1m0a.tst.domb and make sure the scheduled time is not available
        response = self.client.get(reverse('api:realtime-availability') + '?telescope=1m0a.domb.tst')
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertContains(response, '1m0a.domb.tst')
        available_intervals = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals.is_empty())
        # Check that the future scheduled observation interval is not within the available intervals
        blocked_interval = Intervals([(tc_observation.start, tc_observation.end)])
        self.assertTrue(available_intervals.intersect([blocked_interval]).is_empty())
        # Check times before and after the blocked interval
        free_intervals = Intervals([(datetime(2016, 9, 5, 20, 45, tzinfo=timezone.utc),
                                     datetime(2016, 9, 5, 20, 59, tzinfo=timezone.utc)),
                                    (datetime(2016, 9, 5, 22, 1, tzinfo=timezone.utc),
                                     datetime(2016, 9, 5, 22, 15, tzinfo=timezone.utc))])
        self.assertEquals(available_intervals.intersect([free_intervals]), free_intervals)

    def test_realtime_availability_ignores_overlapping_with_future_normal_observations(self):
       # First schedule an normal observation during the time range
        requestgroup = create_simple_requestgroup(
            self.nonstaff_user, self.proposal, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.NORMAL
        requestgroup.save()
        observation = mixer.blend(Observation, request=requestgroup.requests.first(), state='PENDING',
                                     start=datetime(2016, 9, 5, 21, tzinfo=timezone.utc),
                                     end=datetime(2016, 9, 5, 22, tzinfo=timezone.utc),
                                     site='tst', enclosure='domb', telescope='1m0a')
        # Now get availability intervals for 1m0a.tst.domb and make sure the scheduled time is not available
        response = self.client.get(reverse('api:realtime-availability') + '?telescope=1m0a.domb.tst')
        self.assertEqual(response.status_code, 200)
        availability = response.json()
        self.assertContains(response, '1m0a.domb.tst')
        available_intervals = self._convert_availability_to_intervals_helper(availability['1m0a.domb.tst'])
        self.assertFalse(available_intervals.is_empty())
        # Check that the future scheduled observation interval is not within the available intervals
        nonblocked_interval = Intervals([(observation.start, observation.end)])
        self.assertEqual(available_intervals.intersect([nonblocked_interval]), nonblocked_interval)


class TestObservationApiBase(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, id='auto_focus', direct_submission=False)
        self.user = blend_user(user_params={'is_admin': True, 'is_superuser': True, 'is_staff': True})
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.requestgroup = self._generate_requestgroup()
        self.window = self.requestgroup.requests.first().windows.first()
        self.location = self.requestgroup.requests.first().location

    def _generate_requestgroup(self, user=None, proposal=None):
        user = user or self.user
        proposal = proposal or self.proposal
        window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        location = mixer.blend(Location, telescope_class='1m0')
        requestgroup = create_simple_requestgroup(
            user, proposal, window=window, location=location, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.NORMAL
        requestgroup.save()
        return requestgroup

    @staticmethod
    def _generate_observation_data(request_id, configuration_id_list, guide_camera_name='xx03',
                                   start="2016-09-05T22:35:39Z", end="2016-09-05T23:35:40Z"):
        observation = {
            "request": request_id,
            "site": "tst",
            "enclosure": "domb",
            "telescope": "1m0a",
            "start": start,
            "end": end,
            "configuration_statuses": []
        }
        for configuration_id in configuration_id_list:
            config_status = {
                "configuration": configuration_id,
                "instrument_name": "xx03",
            }
            if guide_camera_name:
                config_status["guide_camera_name"] = guide_camera_name
            observation['configuration_statuses'].append(config_status)
        return observation

    def _create_observation(self, observation_json):
        response = self.client.post(reverse('api:observations-list'), data=observation_json)
        self.assertEqual(response.status_code, 201)


class TestPostObservationApi(TestObservationApiBase):
    def setUp(self):
        super().setUp()

    def test_unauthenticated_fails(self):
        self.client.logout()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_authenticated_non_staff_fails(self):
        non_staff_user = blend_user()
        self.client.force_login(non_staff_user)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_non_staff_direct_user_submits_on_other_proposal_fails(self):
        non_staff_user = blend_user()
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, user=non_staff_user, proposal=other_proposal)
        self.client.force_login(non_staff_user)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        # First check if the other proposal is a non direct proposal
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(Observation.objects.all()), 0)
        # Now check if the other proposal is a direct proposal
        self.proposal.direct_submission = True
        self.proposal.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_non_staff_direct_user_submits_to_non_direct_proposal_of_theirs_fails(self):
        non_staff_user = blend_user()
        proposal1 = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, user=non_staff_user, proposal=proposal1)
        proposal2 = mixer.blend(Proposal, direct_submission=False)
        mixer.blend(Membership, user=non_staff_user, proposal=proposal2)
        self.client.force_login(non_staff_user)
        requestgroup = create_simple_requestgroup(
            non_staff_user, proposal2, window=self.window, location=self.location, instrument_type='1M0-SCICAM-SBIG'
        )
        requestgroup.observation_type = RequestGroup.NORMAL
        requestgroup.save()
        observation = self._generate_observation_data(
            requestgroup.requests.first().id, [requestgroup.requests.first().configurations.first().id]
        )
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(Observation.objects.all()), 0)

    def test_non_staff_direct_user_submits_on_own_direct_proposal_succeeds(self):
        self.proposal.direct_submission = True
        self.proposal.save()
        non_staff_user = blend_user()
        mixer.blend(Membership, proposal=self.proposal, user=non_staff_user)
        self.client.force_login(non_staff_user)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(Observation.objects.all()), 1)

    def test_observation_with_valid_instrument_name_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        self.assertEqual(len(Observation.objects.all()), 1)

    def test_multiple_valid_observations_on_same_request_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observations = [observation, observation, observation]
        self._create_observation(observations)
        self.assertEqual(len(Observation.objects.all()), 3)

    def test_multiple_valid_observations_for_multiple_requests_succeeds(self):
        observation1 = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        location = mixer.blend(Location, telescope_class='1m0', telescope='1m0a', site='tst', enclosure='domb')
        requestgroup2 = create_simple_requestgroup(self.user, self.proposal, window=window, location=location)
        configuration = requestgroup2.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SBIG'
        configuration.save()
        observation2 = self._generate_observation_data(
            requestgroup2.requests.first().id, [requestgroup2.requests.first().configurations.first().id]
        )
        observations = [observation1, observation2]
        response = self.client.post(reverse('api:observations-list'), data=observations)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(Observation.objects.all()), 2)

    def test_multiple_configurations_within_an_observation_succeeds(self):
        create_simple_configuration(self.requestgroup.requests.first())
        create_simple_configuration(self.requestgroup.requests.first())
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 3)
        for i, cs in enumerate(ConfigurationStatus.objects.all()):
            self.assertEqual(cs.configuration, self.requestgroup.requests.first().configurations.all()[i])

    def test_cancel_distant_observations_deletes_them(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        self._create_observation(observation)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 0)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 0)

    def test_cancel_close_observations_cancels_them(self):
        self.window.start = datetime(2016, 9, 1, tzinfo=timezone.utc)
        self.window.save()
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation['start'] = "2016-09-02T22:35:39Z"
        observation['end'] = "2016-09-02T23:35:39Z"
        self._create_observation(observation)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        observation_obj = Observation.objects.first()
        self.assertEqual(observation_obj.state, 'CANCELED')

    def test_cancel_current_observations_aborts_them(self):
        self.window.start = datetime(2016, 8, 28, tzinfo=timezone.utc)
        self.window.save()
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation['start'] = "2016-08-31T23:35:39Z"
        observation['end'] = "2016-09-01T01:35:39Z"
        self._create_observation(observation)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        observation_obj = Observation.objects.first()
        self.assertEqual(observation_obj.state, 'ABORTED')

    def test_cancel_current_in_progress_observation_fails(self):
        self.window.start = datetime(2016, 8, 28, tzinfo=timezone.utc)
        self.window.save()
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation['start'] = "2016-08-31T23:35:39Z"
        observation['end'] = "2016-09-01T01:35:39Z"
        self._create_observation(observation)
        obs = Observation.objects.first()
        obs.state = 'IN_PROGRESS'
        obs.save()
        cancel_dict = {'start': "2016-09-01T00:00:00Z", 'end': "2016-09-18T00:00:00Z"}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertContains(response, 'Cannot cancel IN_PROGRESS observations', status_code=400)
        obs.refresh_from_db()
        self.assertEqual(obs.state, 'IN_PROGRESS')

    def test_cancel_current_in_progress_observation_succeeds_with_preemption(self):
        self.window.start = datetime(2016, 8, 28, tzinfo=timezone.utc)
        self.window.save()
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation['start'] = "2016-08-31T23:35:39Z"
        observation['end'] = "2016-09-01T01:35:39Z"
        self._create_observation(observation)
        obs = Observation.objects.first()
        obs.state = 'IN_PROGRESS'
        obs.save()
        cancel_dict = {'start': "2016-09-01T00:00:00Z", 'end': "2016-09-18T00:00:00Z", 'preemption_enabled': True}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        obs.refresh_from_db()
        self.assertEqual(obs.state, 'ABORTED')

    def test_cancel_by_time_range_observations_succeeds(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation2 = copy.deepcopy(observation)
        observation2['start'] = "2016-09-03T22:35:39Z"
        observation2['end'] = "2016-09-03T23:35:39Z"
        self._create_observation([observation, observation2])
        cancel_dict = {'start': "2016-09-04T15:00:00Z", 'end': "2016-09-08T00:00:00Z"}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        self.assertEqual(Observation.objects.first().start, datetime(2016, 9, 3, 22, 35, 39, tzinfo=timezone.utc))

    def test_cancel_by_time_range_and_id_observations_succeeds(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation2 = copy.deepcopy(observation)
        observation2['start'] = "2016-09-04T22:35:39Z"
        observation2['end'] = "2016-09-04T23:35:39Z"
        self._create_observation([observation, observation2])
        cancel_dict = {'ids': [Observation.objects.first().id], 'end': "2016-09-18T00:00:00Z"}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        self.assertEqual(Observation.objects.first().start, datetime(2016, 9, 4, 22, 35, 39, tzinfo=timezone.utc))

    def test_cancel_by_time_range_and_location_observations_succeeds(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        observation2 = copy.deepcopy(observation)
        observation2['start'] = "2016-09-04T22:35:39Z"
        observation2['end'] = "2016-09-04T23:35:39Z"
        observation2['enclosure'] = 'doma'
        observation2['configuration_statuses'][0]['instrument_name'] = 'xx01'
        observation2['configuration_statuses'][0]['guide_camera_name'] = 'xx01'
        self._create_observation([observation, observation2])
        cancel_dict = {'start': "2016-09-01T15:00:00Z",  'end': "2016-09-18T00:00:00Z", 'enclosure': 'domb',
                       'site': 'tst', 'telescope': '1m0a'}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        self.assertEqual(Observation.objects.first().start, datetime(2016, 9, 4, 22, 35, 39, tzinfo=timezone.utc))

    def test_cancel_by_time_range_rapid_response_observations(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        location = mixer.blend(Location, telescope_class='1m0')
        requestgroup2 = create_simple_requestgroup(self.user, self.proposal, window=window, location=location)
        requestgroup2.observation_type = RequestGroup.RAPID_RESPONSE
        requestgroup2.save()
        configuration = requestgroup2.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SBIG'
        configuration.save()
        observation2 = self._generate_observation_data(
            requestgroup2.requests.first().id, [requestgroup2.requests.first().configurations.first().id]
        )
        observation2['enclosure'] = 'doma'
        observation2['configuration_statuses'][0]['instrument_name'] = 'xx01'
        observation2['configuration_statuses'][0]['guide_camera_name'] = 'xx01'

        self._create_observation([observation, observation2])
        cancel_dict = {'start': "2016-09-01T15:00:00Z",  'end': "2016-09-18T00:00:00Z"}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        self.assertEqual(Observation.objects.first().enclosure, 'doma')
        cancel_dict['include_rr'] = True
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 0)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 0)

    def test_cancel_by_time_range_direct_observations(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
                                                      [self.requestgroup.requests.first().configurations.first().id])
        window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        location = mixer.blend(Location, telescope_class='1m0')
        requestgroup2 = create_simple_requestgroup(self.user, self.proposal, window=window, location=location)
        requestgroup2.observation_type = RequestGroup.DIRECT
        requestgroup2.save()
        configuration = requestgroup2.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SBIG'
        configuration.save()
        observation2 = self._generate_observation_data(
            requestgroup2.requests.first().id, [requestgroup2.requests.first().configurations.first().id]
        )
        observation2['enclosure'] = 'doma'
        observation2['configuration_statuses'][0]['instrument_name'] = 'xx01'
        observation2['configuration_statuses'][0]['guide_camera_name'] = 'xx01'

        self._create_observation([observation, observation2])
        cancel_dict = {'start': "2016-09-01T15:00:00Z",  'end': "2016-09-18T00:00:00Z"}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 1)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 1)
        self.assertEqual(Observation.objects.first().enclosure, 'doma')
        cancel_dict['include_direct'] = True
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)
        self.assertEqual(len(Observation.objects.all()), 0)
        self.assertEqual(len(ConfigurationStatus.objects.all()), 0)

    def test_non_staff_direct_user_cancels_observations_in_own_direct_proposal_succeeds(self):
        self.proposal.direct_submission = True
        self.proposal.save()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation([observation])
        other_user = blend_user()
        self.client.force_login(other_user)
        mixer.blend(Membership, proposal=self.proposal, user=other_user)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['canceled'], 1)

    def test_non_staff_direct_user_cancels_observations_in_own_non_direct_proposal_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation([observation])
        other_user = blend_user()
        self.client.force_login(other_user)
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, proposal=self.proposal, user=other_user)
        mixer.blend(Membership, proposal=other_proposal, user=other_user)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.json()['canceled'], 0)

    def test_direct_user_cancels_others_observations_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation([observation])
        other_user = blend_user()
        self.client.force_login(other_user)
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, proposal=other_proposal, user=other_user)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        # Check when the other proposal is not direct submission
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.json()['canceled'], 0)
        # Now check when the other proposal is direct submission
        self.proposal.direct_submission = True
        self.proposal.save()
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.json()['canceled'], 0)

    def test_non_staff_non_direct_user_cancels_observation_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation([observation])
        other_user = blend_user()
        self.client.force_login(other_user)
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cancels_observation_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation([observation])
        self.client.logout()
        cancel_dict = {'ids': [Observation.objects.first().id]}
        response = self.client.post(reverse('api:observations-cancel'), data=cancel_dict)
        self.assertEqual(response.status_code, 403)

    def test_observation_start_must_be_before_end(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-06T22:35:39Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('End time must be after start time', str(response.content))

    def test_observation_not_in_a_request_window_but_overlaps_with_window_start_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-02T23:50:00Z"
        observation['end'] = "2016-09-03T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('times do not fall within any window of the request', str(response.content))

    def test_observation_not_in_a_request_window_but_overlaps_with_window_end_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-05T23:50:00Z"
        observation['end'] = "2016-09-06T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('times do not fall within any window of the request', str(response.content))

    def test_observation_starting_after_request_window_end_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-06T23:50:00Z"
        observation['end'] = "2016-09-07T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('times do not fall within any window of the request', str(response.content))

    def test_observation_ending_before_request_window_start_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-02T00:00:00Z"
        observation['end'] = "2016-09-02T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('times do not fall within any window of the request', str(response.content))

    def test_observation_does_not_match_request_location_site_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        location = self.requestgroup.requests.first().location
        location.site = 'bpl'
        location.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('tst.domb.1m0a does not match the request location', str(response.content))

    def test_observation_does_not_match_request_location_enclosure_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        location = self.requestgroup.requests.first().location
        location.site = 'tst'
        location.enclosure = 'domx'
        location.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('tst.domb.1m0a does not match the request location', str(response.content))

    def test_observation_does_not_match_request_location_telescope_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        location = self.requestgroup.requests.first().location
        location.telescope = '1m0x'
        location.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('tst.domb.1m0a does not match the request location', str(response.content))

    def test_observation_does_not_match_request_location_telescope_class_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        location = self.requestgroup.requests.first().location
        location.telescope_class = '0m4'
        location.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('tst.domb.1m0a does not match the request location', str(response.content))

    def test_unavailable_instrument_type_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        configuration = self.requestgroup.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SINISTRO'
        configuration.save()
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Instrument type 1M0-SCICAM-SINISTRO not available at tst.domb.1m0a', str(response.content))

    def test_unavailable_instrument_name_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['configuration_statuses'][0]['instrument_name'] = 'xx01'
        observation['configuration_statuses'][0]['guide_camera_name'] = 'ef01'
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Instrument xx01 not available at tst.domb.1m0a', str(response.content))

    def test_guide_camera_name_not_required(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id],
            guide_camera_name=None
        )
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(Observation.objects.all()), 1)

    def test_guide_camera_doesnt_match_science_camera_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['configuration_statuses'][0]['instrument_name'] = 'xx01'
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('xx03 is not a valid guide camera for xx01', str(response.content))

    def test_get_current_repeat_from_configuration_status_id(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        create_simple_configuration(request, priority=request.configurations.first().priority + 2)
        request.configuration_repeats = 5
        request.save()
        configurations = list(request.configurations.all())

        observation = self._generate_observation_data(
            request.id,
            [
                configurations[0].id, configurations[1].id, configurations[2].id,
                configurations[0].id, configurations[1].id, configurations[2].id,
                configurations[0].id, configurations[1].id, configurations[2].id,
                configurations[0].id, configurations[1].id, configurations[2].id,
                configurations[0].id, configurations[1].id, configurations[2].id
            ]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        configuration_statuses = observation.configuration_statuses.all()
        self.assertEqual(observation.get_current_repeat(configuration_statuses[2].id), 1)
        self.assertEqual(observation.get_current_repeat(configuration_statuses[3].id), 2)
        self.assertEqual(observation.get_current_repeat(configuration_statuses[7].id), 3)
        self.assertEqual(observation.get_current_repeat(configuration_statuses[10].id), 4)
        self.assertEqual(observation.get_current_repeat(configuration_statuses[14].id), 5)

    def test_get_all_configurations_from_schedule_endpoint_with_repeat_configurations(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        create_simple_configuration(request, priority=request.configurations.first().priority + 2)
        request.configuration_repeats = 5
        request.save()
        configurations = list(request.configurations.all())
        expected_configuration_ids = [
            configurations[0].id, configurations[1].id, configurations[2].id,
            configurations[0].id, configurations[1].id, configurations[2].id,
            configurations[0].id, configurations[1].id, configurations[2].id,
            configurations[0].id, configurations[1].id, configurations[2].id,
            configurations[0].id, configurations[1].id, configurations[2].id
        ]
        observation = self._generate_observation_data(
            request.id,
            expected_configuration_ids
        )
        self._create_observation(observation)
        response = self.client.get(reverse('api:schedule-list'))
        observation = response.json()['results'][0]

        # Ensure configurations are repeated, and configuration statuses are ascending
        previous_configuration_status_id = 0
        previous_priority = 0
        for i, configuration in enumerate(observation['request']['configurations']):
            self.assertEqual(expected_configuration_ids[i], configuration['id'])
            self.assertGreater(configuration['configuration_status'], previous_configuration_status_id)
            self.assertGreater(configuration['priority'], previous_priority)
            previous_priority = configuration['priority']
            previous_configuration_status_id = configuration['configuration_status']


class TestUpdateConfigurationStatusApi(TestObservationApiBase):
    def setUp(self):
        self.summary = {
            'start': "2016-09-02T00:11:22Z",
            'end': "2016-09-02T00:16:33Z",
            'state': "COMPLETED",
            'time_completed': 920,
            'events': [
                {
                    'time': "2016-09-02T00:11:22Z",
                    'description': "EnclosureOpen Command",
                    'state': "IN_PROGRESS"
                },
                {
                    'time': "2016-09-02T00:11:52Z",
                    'description': "EnclosureOpen Command",
                    'state': "COMPLETED"
                },
                {
                    'time': "2016-09-02T00:12:12Z",
                    'description': "StartExposureCommand",
                    'state': "IN_PROGRESS"
                },
                {
                    'time': "2016-09-02T00:15:43Z",
                    'description': "StartExposureCommand",
                    'state': "COMPLETED"
                }
            ]
        }
        super().setUp()

    def test_update_configuration_state_only_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        update_data = {'state': 'ATTEMPTED'}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'ATTEMPTED')

    def test_dont_update_configuration_state_from_terminal_state(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        update_data = {'state': 'COMPLETED'}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'COMPLETED')
        update_data = {'state': 'ABORTED'}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'COMPLETED')

    def test_dont_update_other_fields_in_configuration_state(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        update_data = {'state': 'COMPLETED', 'instrument_name': 'fake01', 'guide_camera_name': 'fake01'}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'COMPLETED')
        self.assertNotEqual(configuration_status.instrument_name, 'fake01')
        self.assertNotEqual(configuration_status.guide_camera_name, 'fake01')

    def test_update_summary_in_configuration_state_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        update_data = {'state': 'COMPLETED', 'summary': self.summary}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'COMPLETED')
        self.assertEqual(configuration_status.summary.state, self.summary['state'])
        self.assertEqual(configuration_status.summary.reason, '')
        self.assertEqual(configuration_status.summary.start, parse(self.summary['start']))
        self.assertEqual(configuration_status.summary.end, parse(self.summary['end']))
        self.assertEqual(configuration_status.summary.time_completed, self.summary['time_completed'])
        self.assertEqual(configuration_status.summary.events, self.summary['events'])

    def test_update_summary_already_exists_in_configuration_state_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        update_data = {'state': 'COMPLETED', 'summary': self.summary}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'COMPLETED')
        self.assertEqual(configuration_status.summary.state, self.summary['state'])
        summary = copy.deepcopy(self.summary)
        summary['state'] = 'ABORTED'
        summary['reason'] = 'Ran out of time'
        update_data = {'summary': summary}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.summary.state, 'ABORTED')
        self.assertEqual(len(Summary.objects.all()), 1)

    def test_update_incomplete_summary_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        summary = copy.deepcopy(self.summary)
        del summary['state']

        update_data = {'state': 'COMPLETED', 'summary': summary}
        configuration_status = ConfigurationStatus.objects.first()
        response = self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('state', response.json().keys())

    def test_update_summary_triggers_request_status_update(self):
        # set up request group to have a configuration with just enough time to be completed
        instrument_config = self.requestgroup.requests.first().configurations.first().instrument_configs.first()
        instrument_config.exposure_time = 92
        instrument_config.exposure_count = 10
        instrument_config.save()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        update_data = {'state': 'FAILED', 'summary': self.summary}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'FAILED')
        request = self.requestgroup.requests.first()
        request.refresh_from_db()
        self.assertEqual(request.state, 'COMPLETED')
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')

    def test_update_summary_triggers_request_status_without_completing(self):
        # set up request group to have a configuration with just enough time to be completed
        instrument_config = self.requestgroup.requests.first().configurations.first().instrument_configs.first()
        instrument_config.exposure_time = 92
        instrument_config.exposure_count = 12
        instrument_config.save()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        update_data = {'state': 'FAILED', 'summary': self.summary}
        configuration_status = ConfigurationStatus.objects.first()
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        configuration_status.refresh_from_db()
        self.assertEqual(configuration_status.state, 'FAILED')
        request = self.requestgroup.requests.first()
        request.refresh_from_db()
        self.assertEqual(request.state, 'PENDING')
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'PENDING')

    def test_update_configuration_status_end_time_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        self.assertEqual(observation.end, new_end)

    def test_update_configuration_status_end_time_with_repeat_configurations_succeeds(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        request.configuration_repeats = 3
        request.save()
        configurations = list(request.configurations.all())
        configuration_1_duration = configurations[0].duration
        configuration_2_duration = configurations[1].duration

        observation = self._generate_observation_data(
            request.id,
            [configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id]
        )
        self._create_observation(observation)
        configuration_statuses = ConfigurationStatus.objects.all()
        new_config_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_config_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_statuses[0].id,)), update_data)
        observation = Observation.objects.first()
        slew_and_oe_switching_time = 10 # 3 * minimum slew of 2s + 2 * oe change time of 2s
        new_observation_end = new_config_end + timedelta(seconds=(configuration_1_duration*2 + configuration_2_duration*3 + slew_and_oe_switching_time))
        self.assertEqual(observation.end, new_observation_end)

    def test_update_configuration_status_end_time_with_repeat_configurations_mid_repeat_succeeds(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        request.configuration_repeats = 3
        request.save()
        configurations = list(request.configurations.all())
        configuration_1_duration = configurations[0].duration
        configuration_2_duration = configurations[1].duration

        observation = self._generate_observation_data(
            request.id,
            [configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id]
        )
        self._create_observation(observation)
        configuration_statuses = ConfigurationStatus.objects.all()
        new_config_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_config_end, '%Y-%m-%dT%H:%M:%SZ')}
        # Updating configuration status 2, so there should be 3 left to add to end time
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_statuses[2].id,)), update_data)
        observation = Observation.objects.first()
        slew_and_oe_switching_time = 6 # 2 * minimum slew of 2s + 1 * oe change time of 2s
        new_observation_end = new_config_end + timedelta(seconds=(configuration_1_duration*1 + configuration_2_duration*2 + slew_and_oe_switching_time))
        self.assertEqual(observation.end, new_observation_end)

    def test_update_configuration_status_update_start_time_with_repeat_configurations_last_repeat_succeeds(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        request.configuration_repeats = 3
        request.save()
        configurations = list(request.configurations.all())
        configuration_1_duration = configurations[0].duration
        configuration_2_duration = configurations[1].duration

        observation = self._generate_observation_data(
            request.id,
            [configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id]
        )
        self._create_observation(observation)
        configuration_statuses = ConfigurationStatus.objects.all()
        new_config_start = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(new_config_start, '%Y-%m-%dT%H:%M:%SZ')}
        # Updating configuration status 2, so there should be 3 left to add to end time
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_statuses[4].id,)), update_data)
        observation = Observation.objects.first()
        config_front_padding = 14  # not used for the current configuration 16s front padding - 2s oe change time
        new_observation_end = new_config_start + timedelta(seconds=(configuration_1_duration*1 + configuration_2_duration*1 - config_front_padding))
        self.assertEqual(observation.end, new_observation_end)

    def test_update_configuration_status_exposure_start_time_succeeds(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()
        end_time = datetime(2016, 9, 5, 23, 35, 40).replace(tzinfo=timezone.utc)
        exposure_start = datetime(2016, 9, 5, 22, 45, 22).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(exposure_start, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        self.assertGreater(observation.end, exposure_start)
        self.assertGreater(end_time, observation.end)

    def test_lengthen_first_configuration_status_end_time_with_multiple_configs(self):
        create_simple_configuration(self.requestgroup.requests.first(), priority=2)
        create_simple_configuration(self.requestgroup.requests.first(), priority=3)
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        new_obs_end = new_end + timedelta(seconds=self.requestgroup.requests.first().get_remaining_duration(
            configuration_status.configuration.priority))
        self.assertEqual(observation.end, new_obs_end)

    def test_lengthen_first_configuration_status_exposure_start_with_multiple_configs(self):
        create_simple_configuration(self.requestgroup.requests.first(), priority=2)
        create_simple_configuration(self.requestgroup.requests.first(), priority=3)
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        exposure_start = datetime(2016, 9, 5, 22, 45, 22).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(exposure_start, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        new_obs_end = exposure_start + timedelta(seconds=self.requestgroup.requests.first().get_remaining_duration(
            configuration_status.configuration.priority, include_current=True))
        self.assertEqual(observation.end, new_obs_end)

    def test_shorten_first_configuration_status_end_time_with_multiple_configs(self):
        create_simple_configuration(self.requestgroup.requests.first(), priority=2)
        create_simple_configuration(self.requestgroup.requests.first(), priority=3)
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        new_end = datetime(2016, 9, 5, 23, 13, 31).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        new_obs_end = new_end + timedelta(seconds=self.requestgroup.requests.first().get_remaining_duration(
            configuration_status.configuration.priority))
        self.assertEqual(observation.end, new_obs_end)

    def test_shorten_first_configuration_status_exposure_start_with_multiple_configs(self):
        create_simple_configuration(self.requestgroup.requests.first(), priority=2)
        create_simple_configuration(self.requestgroup.requests.first(), priority=3)
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        exposure_start = datetime(2016, 9, 5, 22, 35, 45).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(exposure_start, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        new_obs_end = exposure_start + timedelta(seconds=self.requestgroup.requests.first().get_remaining_duration(
            configuration_status.configuration.priority, include_current=True))
        self.assertEqual(observation.end, new_obs_end)

    def test_shorten_first_configuration_status_exposure_start_with_repeat_configurations_multiple_configs(self):
        requestgroup = self._generate_requestgroup()
        request = requestgroup.requests.first()
        create_simple_configuration(request, priority=request.configurations.first().priority + 1)
        request.configuration_repeats = 3
        request.save()
        configurations = list(request.configurations.all())
        configuration_1_duration = configurations[0].duration
        configuration_2_duration = configurations[1].duration

        observation = self._generate_observation_data(
            request.id,
            [configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id, configurations[0].id, configurations[1].id]
        )
        self._create_observation(observation)
        configuration_statuses = ConfigurationStatus.objects.all()
        new_config_start = datetime(2016, 9, 5, 22, 35, 45).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(new_config_start, '%Y-%m-%dT%H:%M:%SZ')}
        # Updating configuration status 1, so there should be 4 left to add to end time
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_statuses[1].id,)), update_data)
        observation = Observation.objects.first()
        config_front_padding = 8  # not used for the current configuration 16s front padding - 2*2s minimum slew and 2*2s oe change time
        new_observation_end = new_config_start + timedelta(seconds=(configuration_1_duration*2 + configuration_2_duration*3 - config_front_padding))
        self.assertEqual(observation.end, new_observation_end)

    def test_configuration_status_exposure_start_cant_be_before_observation_start(self):
        observation = self._generate_observation_data(self.requestgroup.requests.first().id,
            [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.first()

        end_time = datetime(2016, 9, 5, 23, 35, 40).replace(tzinfo=timezone.utc)
        exposure_start = datetime(2016, 9, 5, 22, 33, 0).replace(tzinfo=timezone.utc)
        update_data = {"exposures_start_at": datetime.strftime(exposure_start, '%Y-%m-%dT%H:%M:%SZ')}
        response = self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Updated exposure start time must be after the observation start time', str(response.content))
        observation = Observation.objects.first()
        self.assertEqual(observation.end, end_time)

    def test_update_last_configuration_status_end_time_is_same_as_obs_end(self):
        create_simple_configuration(self.requestgroup.requests.first(), priority=2)
        create_simple_configuration(self.requestgroup.requests.first(), priority=3)
        configuration_ids = [config.id for config in self.requestgroup.requests.first().configurations.all()]
        observation = self._generate_observation_data(self.requestgroup.requests.first().id, configuration_ids)
        self._create_observation(observation)
        configuration_status = ConfigurationStatus.objects.last()

        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:configurationstatus-detail', args=(configuration_status.id,)), update_data)
        observation = Observation.objects.first()
        new_obs_end = new_end + timedelta(seconds=self.requestgroup.requests.first().get_remaining_duration(
            configuration_status.configuration.priority))
        self.assertEqual(new_obs_end, new_end)
        self.assertEqual(observation.end, new_obs_end)


class TestUpdateObservationApi(TestObservationApiBase):
    def setUp(self):
        super().setUp()

    @staticmethod
    def _create_clone_observation(observation, start, end):
        return mixer.blend(
            Observation,
            site=observation.site,
            enclosure=observation.enclosure,
            telescope=observation.telescope,
            start=start.replace(tzinfo=timezone.utc),
            end=end.replace(tzinfo=timezone.utc),
            request=observation.request
        )

    def test_update_observation_end_time_succeeds(self):
        original_end = datetime(2016, 9, 5, 23, 35, 40).replace(tzinfo=timezone.utc)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        self.assertEqual(observation.end, original_end)

        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        observation.refresh_from_db()
        self.assertEqual(observation.end, new_end)

    def test_update_observation_end_time_cancels_proper_overlapping_observations(self):
        self.window.start = datetime(2016, 9, 1, tzinfo=timezone.utc)
        self.window.save()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id],
            start="2016-09-02T22:35:39Z",
            end="2016-09-02T23:35:40Z"
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        cancel_obs_1 = self._create_clone_observation(observation, datetime(2016, 9, 2, 23, 35, 41), datetime(2016, 9, 2, 23, 39, 59))
        cancel_obs_2 = self._create_clone_observation(observation, datetime(2016, 9, 2, 23, 42, 0), datetime(2016, 9, 2, 23, 55, 34))
        extra_obs_1 = self._create_clone_observation(observation, datetime(2016, 9, 2, 23, 55, 35), datetime(2016, 9, 3, 0, 14, 21))
        rr_obs_1 = self._create_clone_observation(observation, datetime(2016, 9, 2, 23, 40, 0), datetime(2016, 9, 2, 23, 41, 59))
        location = mixer.blend(Location, telescope_class='1m0')
        rr_requestgroup = create_simple_requestgroup(self.user, self.proposal, window=self.window, location=location)
        rr_requestgroup.observation_type = RequestGroup.RAPID_RESPONSE
        rr_requestgroup.save()
        rr_obs_1.request = rr_requestgroup.requests.first()
        rr_obs_1.save()

        new_end = datetime(2016, 9, 2, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        observation.refresh_from_db()
        self.assertEqual(observation.end, new_end)
        cancel_obs_1.refresh_from_db()
        self.assertEqual(cancel_obs_1.state, 'CANCELED')
        cancel_obs_2.refresh_from_db()
        self.assertEqual(cancel_obs_2.state, 'CANCELED')
        extra_obs_1.refresh_from_db()
        self.assertEqual(extra_obs_1.state, 'PENDING')
        rr_obs_1.refresh_from_db()
        self.assertEqual(rr_obs_1.state, 'PENDING')

    def test_update_observation_end_time_rr_cancels_overlapping_rr(self):
        self.window.start = datetime(2016, 9, 1, tzinfo=timezone.utc)
        self.window.save()
        self.requestgroup.observation_type = RequestGroup.RAPID_RESPONSE
        self.requestgroup.save()
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id],
            start="2016-09-02T22:35:39Z",
            end="2016-09-02T23:35:40Z"
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        cancel_obs_1 = self._create_clone_observation(observation, datetime(2016, 9, 2, 23, 35, 41), datetime(2016, 9, 2, 23, 39, 59))
        new_end = datetime(2016, 9, 2, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        cancel_obs_1.refresh_from_db()
        self.assertEqual(cancel_obs_1.state, 'CANCELED')

    def test_update_observation_end_before_start_does_nothing(self):
        original_end = datetime(2016, 9, 5, 23, 35, 40).replace(tzinfo=timezone.utc)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()

        new_end = datetime(2016, 9, 5, 19, 35, 40).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        observation.refresh_from_db()
        self.assertEqual(observation.end, original_end)

    def test_update_observation_end_must_be_in_future(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()

        new_end = datetime(2016, 8, 5, 19, 35, 40).replace(tzinfo=timezone.utc)
        update_data = {"end": datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['non_field_errors'], ['Updated end time must be in the future'])

    def test_update_observation_update_must_include_end(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()

        update_data = {'field_1': 'testtest', 'not_end': 2341}
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['non_field_errors'], ['Observation update must include `end` field'])

    def test_update_observation_non_staff_non_direct_user_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        original_end = observation.end
        non_staff_user = blend_user()
        mixer.blend(Membership, user=non_staff_user, proposal=self.proposal)
        self.client.force_login(non_staff_user)
        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {'end': datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 403)
        observation.refresh_from_db()
        self.assertEqual(original_end, observation.end)

    def test_update_observation_unauthenticated_fails(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        original_end = observation.end
        self.client.logout()
        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {'end': datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 403)
        observation.refresh_from_db()
        self.assertEqual(original_end, observation.end)

    def test_update_observation_non_staff_direct_user_on_own_proposals(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        original_end = observation.end
        non_staff_user = blend_user()
        mixer.blend(Membership, user=non_staff_user, proposal=self.proposal)
        self.client.force_login(non_staff_user)
        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {'end': datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        # Check when the proposal is not direct. Should fail.
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 403)
        observation.refresh_from_db()
        self.assertEqual(original_end, observation.end)
        # Check when the proposal is direct. Should succeed.
        self.proposal.direct_submission = True
        self.proposal.save()
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 200)
        observation.refresh_from_db()
        self.assertEqual(new_end, observation.end)

    def test_update_observation_non_staff_direct_user_on_other_proposals_fail(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)
        observation = Observation.objects.first()
        original_end = observation.end
        non_staff_user = blend_user()
        other_proposal = mixer.blend(Proposal, direct_submission=True)
        mixer.blend(Membership, user=non_staff_user, proposal=other_proposal)
        self.client.force_login(non_staff_user)
        new_end = datetime(2016, 9, 5, 23, 47, 22).replace(tzinfo=timezone.utc)
        update_data = {'end': datetime.strftime(new_end, '%Y-%m-%dT%H:%M:%SZ')}
        # Check when the other proposal is not direct submission
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 404)  # 404 because this user cannot even see the observation
        observation.refresh_from_db()
        self.assertEqual(original_end, observation.end)
        # Check when the other proposal is direct submission
        self.proposal.direct_submission = True
        self.proposal.save()
        response = self.client.patch(reverse('api:observations-detail', args=(observation.id,)), update_data)
        self.assertEqual(response.status_code, 404)  # 404 because this user cannot even see the observation
        observation.refresh_from_db()
        self.assertEqual(original_end, observation.end)


class TestLastScheduled(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.proposal.direct_submission = True
        self.proposal.save()
        # Mock the cache with a real one for these tests
        self.locmem_cache = caches.create_connection('testlocmem')
        self.locmem_cache.clear()
        self.patch1 = patch.object(views, 'cache', self.locmem_cache)
        self.patch1.start()
        self.patch2 = patch.object(viewsets, 'cache', self.locmem_cache)
        self.patch2.start()

    def tearDown(self):
        super().tearDown()
        self.patch1.stop()
        self.patch2.stop()

    def test_last_schedule_date_is_7_days_out_if_no_cached_value(self):
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)

        response = self.client.get(reverse('api:last_scheduled'))
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))

    def test_last_schedule_date_is_updated_when_single_observation_is_submitted(self):
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        self._create_observation(observation)

        response = self.client.get(reverse('api:last_scheduled') + "?site=tst")
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now(), delta=timedelta(minutes=1))

        # Verify that the last scheduled time for a different site isn't updated
        response = self.client.get(reverse('api:last_scheduled') + "?site=non")
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))

    def test_last_schedule_date_is_updated_when_multiple_observations_are_submitted(self):
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observations = [observation, observation, observation]
        self._create_observation(observations)

        response = self.client.get(reverse('api:last_scheduled'))
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now(), delta=timedelta(minutes=1))

    def test_last_schedule_date_is_updated_when_single_direct_submission_is_submitted(self):
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        direct_submission = copy.deepcopy(observation)
        response = self.client.post(reverse('api:schedule-list'), data=direct_submission)
        self.assertEqual(response.status_code, 201)
        response = self.client.get(reverse('api:last_scheduled') + "?site=tst")
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now(), delta=timedelta(minutes=1))

    def test_last_schedule_date_is_updated_when_multiple_direct_submissions_are_submitted(self):
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        direct_submissions = [copy.deepcopy(observation), copy.deepcopy(observation), copy.deepcopy(observation)]
        response = self.client.post(reverse('api:schedule-list'), data=direct_submissions)
        self.assertEqual(response.status_code, 201)
        response = self.client.get(reverse('api:last_scheduled') + "?site=tst")
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now(), delta=timedelta(minutes=1))

    def test_last_schedule_date_is_not_updated_when_observation_is_mixed(self):
        mixer.blend(Observation, request=self.requestgroup.requests.first())
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        response = self.client.get(reverse('api:last_scheduled'))
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))


class TestTimeAccountingBase(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.time_allocation = mixer.blend(TimeAllocation, instrument_types=['1M0-SCICAM-SBIG'], semester=self.semester,
                                           proposal=self.proposal, std_allocation=100, rr_allocation=100,
                                           tc_allocation=100, ipp_time_available=100)

    @staticmethod
    def _create_observation_and_config_status(requestgroup, start, end, config_state='PENDING'):
        observation = mixer.blend(Observation, request=requestgroup.requests.first(),
                                  site='tst', enclosure='domb', telescope='1m0a',
                                  start=start, end=end, state='PENDING')
        config_status = mixer.blend(ConfigurationStatus, observation=observation,
                                    configuration=requestgroup.requests.first().configurations.first(),
                                    instrument_name='xx03', guide_camera_name='xx03', state=config_state)

        return observation, config_status

    def _helper_test_summary_save(self, observation_type=RequestGroup.NORMAL, config_status_state='PENDING',
                                  config_start=datetime(2019, 9, 5, 22, 20, 24, tzinfo=timezone.utc),
                                  config_end=datetime(2019, 9, 5, 22, 21, 24, tzinfo=timezone.utc)):
        self.assertEqual(self.time_allocation.std_time_used, 0)
        self.assertEqual(self.time_allocation.tc_time_used, 0)
        self.assertEqual(self.time_allocation.rr_time_used, 0)
        self.requestgroup.observation_type = observation_type
        self.requestgroup.save()
        _, config_status = self._create_observation_and_config_status(self.requestgroup,
                                                                      start=datetime(2019, 9, 5, 22, 20,
                                                                                     tzinfo=timezone.utc),
                                                                      end=datetime(2019, 9, 5, 23, tzinfo=timezone.utc),
                                                                      config_state=config_status_state)
        self.assertEqual(config_status.time_charged, 0)
        summary = mixer.blend(Summary, configuration_status=config_status, start=config_start, end=config_end)
        self.time_allocation.refresh_from_db()
        time_used = configuration_time_used(summary, observation_type).total_seconds() / 3600.0
        if observation_type == RequestGroup.NORMAL:
            self.assertAlmostEqual(self.time_allocation.std_time_used, time_used, 5)
            self.assertEqual(self.time_allocation.tc_time_used, 0)
            self.assertEqual(self.time_allocation.rr_time_used, 0)
        if observation_type == RequestGroup.RAPID_RESPONSE:
            self.assertAlmostEqual(self.time_allocation.rr_time_used, time_used, 5)
            self.assertEqual(self.time_allocation.std_time_used, 0)
            self.assertEqual(self.time_allocation.tc_time_used, 0)
        if observation_type == RequestGroup.TIME_CRITICAL:
            self.assertAlmostEqual(self.time_allocation.tc_time_used, time_used, 5)
            self.assertEqual(self.time_allocation.rr_time_used, 0)
            self.assertEqual(self.time_allocation.std_time_used, 0)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_used, 5)
        return config_status, summary


class TestTimeAccounting(TestTimeAccountingBase):
    def test_attempted_configuration_status_affects_normal_time_accounting(self):
        self._helper_test_summary_save(config_status_state='ATTEMPTED')

    def test_failed_configuration_status_affects_normal_time_accounting(self):
        self._helper_test_summary_save(config_status_state='FAILED',
                                       config_end=datetime(2019, 9, 5, 22, 40, 24, tzinfo=timezone.utc))

    def test_completed_configuration_status_affects_tc_time_accounting(self):
        self._helper_test_summary_save(observation_type=RequestGroup.TIME_CRITICAL,
                                       config_status_state='COMPLETED',
                                       config_end=datetime(2019, 9, 5, 22, 58, 24, tzinfo=timezone.utc))

    def test_completed_configuration_status_affects_rr_time_accounting(self):
        self._helper_test_summary_save(observation_type=RequestGroup.RAPID_RESPONSE,
                                       config_status_state='COMPLETED',
                                       config_end=datetime(2019, 9, 5, 22, 21, 24, tzinfo=timezone.utc))

    def test_completed_configuration_status_affects_rr_time_accounting_block_bounded(self):
        self._helper_test_summary_save(observation_type=RequestGroup.RAPID_RESPONSE,
                                       config_status_state='COMPLETED',
                                       config_end=datetime(2019, 9, 5, 22, 58, 24, tzinfo=timezone.utc))

    def test_multiple_summary_saves_leads_to_consistent_time_accounting(self):
        config_start = datetime(2019, 9, 5, 22, 20, 24, tzinfo=timezone.utc)
        config_status, summary = self._helper_test_summary_save(
            observation_type=RequestGroup.NORMAL,
            config_status_state='ATTEMPTED',
            config_start=config_start,
            config_end=datetime(2019, 9, 5, 22, 58, 24, tzinfo=timezone.utc)
        )

        config_status.state = 'FAILED'
        config_status.save()
        new_end_time = datetime(2019, 9, 5, 22, 30, tzinfo=timezone.utc)
        summary.end = new_end_time
        summary.save()
        self.time_allocation.refresh_from_db()

        time_used = (new_end_time - config_start).total_seconds() / 3600.0
        self.assertAlmostEqual(self.time_allocation.std_time_used, time_used, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_used)

        new_end_time = datetime(2019, 9, 5, 22, 59, 33, tzinfo=timezone.utc)
        summary.end = new_end_time
        summary.save()
        self.time_allocation.refresh_from_db()

        time_used = (new_end_time - config_start).total_seconds() / 3600.0
        self.assertAlmostEqual(self.time_allocation.std_time_used, time_used, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_used)

    def test_multiple_requests_leads_to_consistent_time_accounting(self):
        self._helper_test_summary_save(
            observation_type=RequestGroup.NORMAL,
            config_status_state='COMPLETED',
            config_end=datetime(2019, 9, 5, 22, 58, 24, tzinfo=timezone.utc)
        )
        self.time_allocation.refresh_from_db()
        total_time_used = self.time_allocation.std_time_used

        window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        location = mixer.blend(Location, telescope_class='1m0')
        second_requestgroup = create_simple_requestgroup(self.user, self.proposal, window=window,
                                                       location=location)
        second_requestgroup.observation_type = RequestGroup.NORMAL
        second_requestgroup.save()
        configuration = second_requestgroup.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SBIG'
        configuration.save()
        _, second_config_status = self._create_observation_and_config_status(second_requestgroup,
                                                                             start=datetime(2019, 9, 6, 23, 20,
                                                                                            tzinfo=timezone.utc),
                                                                             end=datetime(2019, 9, 6, 23, 50,
                                                                                          tzinfo=timezone.utc),
                                                                             config_state='COMPLETED')

        config_start = datetime(2019, 9, 6, 23, 20, 24, tzinfo=timezone.utc)
        config_end = datetime(2019, 9, 6, 23, 40, 24, tzinfo=timezone.utc)
        mixer.blend(Summary, configuration_status=second_config_status, start=config_start, end=config_end)
        self.time_allocation.refresh_from_db()
        time_used = (config_end - config_start).total_seconds() / 3600.0
        total_time_used += time_used
        self.assertAlmostEqual(self.time_allocation.std_time_used, total_time_used, 5)
        second_config_status.refresh_from_db()
        self.assertAlmostEqual(second_config_status.time_charged, time_used, 5)


class TestRefundTime(TestTimeAccountingBase):
    def test_refund_pending_configuration_status_does_nothing(self):
        config_status, _ = self._helper_test_summary_save(config_status_state='PENDING')
        time_refunded = refund_configuration_status_time(config_status, 1.0)
        self.assertEqual(time_refunded, 0.0)

    def test_refund_configuration_status_with_no_summary_does_nothing(self):
        observation, config_status = self._create_observation_and_config_status(self.requestgroup,
                                                                      start=datetime(2019, 9, 5, 22, 20,
                                                                                     tzinfo=timezone.utc),
                                                                      end=datetime(2019, 9, 5, 23, tzinfo=timezone.utc),
                                                                      config_state='ATTEMPTED')
        self.assertEqual(config_status.time_charged, 0)
        time_refunded = refund_configuration_status_time(config_status, 1.0)
        self.assertEqual(time_refunded, 0.0)
        time_refunded = refund_observation_time(observation, 1.0)
        self.assertEqual(time_refunded, 0.0)

    def test_refund_configuration_status_100_percent_succeeds(self):
        config_start = datetime(2019, 9, 5, 22, 20, tzinfo=timezone.utc)
        config_end = datetime(2019, 9, 5, 23, tzinfo=timezone.utc)
        time_charged = (config_end - config_start).total_seconds() / 3600.0
        config_status, _ = self._helper_test_summary_save(
            config_status_state='COMPLETED',
            config_start=config_start,
            config_end=config_end
        )
        self.assertAlmostEqual(config_status.time_charged, time_charged, 5)
        time_refunded = refund_configuration_status_time(config_status, 1.0)
        self.assertAlmostEqual(time_refunded, time_charged, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, 0.0, 5)

    def test_refund_configuration_status_50_percent_succeeds(self):
        config_start = datetime(2019, 9, 5, 22, 20, tzinfo=timezone.utc)
        config_end = datetime(2019, 9, 5, 23, tzinfo=timezone.utc)
        time_charged = (config_end - config_start).total_seconds() / 3600.0
        config_status, _ = self._helper_test_summary_save(
            config_status_state='COMPLETED',
            config_start=config_start,
            config_end=config_end
        )
        refund_ratio = 0.5
        self.assertAlmostEqual(config_status.time_charged, time_charged, 5)
        time_refunded = refund_configuration_status_time(config_status, refund_ratio)
        self.assertAlmostEqual(time_refunded, time_charged * refund_ratio, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_charged * refund_ratio, 5)

    def test_refund_configuration_status_cant_refund_beyond_time_charged(self):
        config_start = datetime(2019, 9, 5, 22, 20, tzinfo=timezone.utc)
        config_end = datetime(2019, 9, 5, 23, tzinfo=timezone.utc)
        time_charged = (config_end - config_start).total_seconds() / 3600.0
        config_status, _ = self._helper_test_summary_save(
            config_status_state='COMPLETED',
            config_start=config_start,
            config_end=config_end
        )
        refund_ratio_1 = 0.6
        self.assertAlmostEqual(config_status.time_charged, time_charged, 5)
        time_refunded = refund_configuration_status_time(config_status, refund_ratio_1)
        self.assertAlmostEqual(time_refunded, time_charged * refund_ratio_1, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_charged * (1-refund_ratio_1), 5)

        # Already refunded 60% of time, so refunding 25% of time will do nothing
        refund_ratio_2 = 0.25
        time_refunded = refund_configuration_status_time(config_status, refund_ratio_2)
        self.assertAlmostEqual(time_refunded, 0.0, 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, time_charged * (1-refund_ratio_1), 5)

        # Now refunding 100% of the time will just refund the rest of the time, not an additional 100%
        refund_ratio_3 = 1.0
        time_refunded = refund_configuration_status_time(config_status, refund_ratio_3)
        self.assertAlmostEqual(time_refunded, time_charged * (1-refund_ratio_1), 5)
        config_status.refresh_from_db()
        self.assertAlmostEqual(config_status.time_charged, 0.0, 5)

    def test_refund_observation_refunds_all_configuration_status_within_it(self):
        observation, config_status_1 = self._create_observation_and_config_status(
            self.requestgroup,
            start=datetime(2019, 9, 5, 22, 20, tzinfo=timezone.utc),
            end=datetime(2019, 9, 5, 22, 31, tzinfo=timezone.utc),
            config_state='ATTEMPTED'
        )
        original_std_time_used = self.time_allocation.std_time_used
        summary_1 = mixer.blend(Summary, configuration_status=config_status_1,
                                start=datetime(2019, 9, 5, 22, 20, tzinfo=timezone.utc),
                                end=datetime(2019, 9, 5, 22, 25, tzinfo=timezone.utc))
        config_status_2 = mixer.blend(ConfigurationStatus, observation=observation,
                                      configuration=config_status_1.configuration,
                                      instrument_name='xx03', guide_camera_name='xx03', state='COMPLETED')
        summary_2 = mixer.blend(Summary, configuration_status=config_status_2,
                                start=datetime(2019, 9, 5, 22, 25, tzinfo=timezone.utc),
                                end=datetime(2019, 9, 5, 22, 31, tzinfo=timezone.utc))
        self.time_allocation.refresh_from_db()
        std_time_used = self.time_allocation.std_time_used
        # Verify initial time charged is correct
        time_used_1 = configuration_time_used(summary_1, 'NORMAL').total_seconds() / 3600.0
        time_used_2 = configuration_time_used(summary_2, 'NORMAL').total_seconds() / 3600.0
        config_status_1.refresh_from_db()
        self.assertAlmostEqual(config_status_1.time_charged, time_used_1)
        config_status_2.refresh_from_db()
        self.assertAlmostEqual(config_status_2.time_charged, time_used_2)
        # Now refund the entire observation and see that each configuration is refunded
        total_refunded = refund_observation_time(observation, 1.0)
        self.assertAlmostEqual(total_refunded, (time_used_1 + time_used_2))
        config_status_1.refresh_from_db()
        self.assertAlmostEqual(config_status_1.time_charged, 0.0)
        config_status_2.refresh_from_db()
        self.assertAlmostEqual(config_status_2.time_charged, 0.0)
        self.time_allocation.refresh_from_db()
        self.assertGreater(std_time_used, self.time_allocation.std_time_used)
        self.assertAlmostEqual(self.time_allocation.std_time_used, original_std_time_used)


class TestTimeAccountingCommand(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.time_allocation = mixer.blend(TimeAllocation, instrument_types=['1M0-SCICAM-SBIG'], semester=self.semester,
                                           proposal=self.proposal, std_allocation=100, rr_allocation=100,
                                           tc_allocation=100, ipp_time_available=100)

    def _add_observation(self, state, time_completed):
        observation = Observation.objects.create(request=self.requestgroup.requests.first(), state=state, site='tst', enclosure='domb', telescope='1m0a',
        start=datetime(2016,9,5,22,35,39, tzinfo=timezone.utc), end=datetime(2016,9,5,23,35,40, tzinfo=timezone.utc))
        config_status = ConfigurationStatus.objects.create(observation=observation, configuration=self.requestgroup.requests.first().configurations.first(),
        state=state, instrument_name='xx03', guide_camera_name='xx03')
        Summary.objects.create(configuration_status=config_status, start=datetime(2016,9,5,22,35,39, tzinfo=timezone.utc),
        end=datetime(2016,9,5,23,35,40, tzinfo=timezone.utc), time_completed=time_completed, state=state)
        return observation

    def test_with_no_obs_command_reports_no_time_used(self):
        command_output = StringIO()
        command_err = StringIO()
        call_command('time_accounting', f'-p{self.proposal.id}', '-i1M0-SCICAM-SBIG', f'-s{self.semester.id}', stdout=command_output, stderr=command_err)
        command_out = command_output.getvalue()
        self.assertIn('Used 0 NORMAL hours, 0 RAPID_RESPONSE hours, and 0 TIME_CRITICAL hours', command_out)
        self.assertNotIn('is different from existing', command_err)
        self.time_allocation.refresh_from_db()
        self.assertEqual(self.time_allocation.std_time_used, 0)
        self.assertEqual(self.time_allocation.rr_time_used, 0)
        self.assertEqual(self.time_allocation.tc_time_used, 0)

    def test_with_one_obs_command_reports_time_used_and_modifies_time(self):
        command_output = StringIO()
        command_err = StringIO()
        observation = self._add_observation(state='COMPLETED', time_completed=1000)
        # reset time used to 0 since creating the observation already modified it
        self.time_allocation.std_time_used = 0
        self.time_allocation.save()
        call_command('time_accounting', f'-p{self.proposal.id}', '-i1M0-SCICAM-SBIG', f'-s{self.semester.id}', stdout=command_output, stderr=command_err)
        time_used = (observation.configuration_statuses.first().summary.end - observation.configuration_statuses.first().summary.start).total_seconds() / 3600.0
        self.assertIn(f'Used {time_used} NORMAL hours, 0 RAPID_RESPONSE hours, and 0 TIME_CRITICAL hours', command_output.getvalue())
        self.assertIn('is different from existing', command_err.getvalue())
        self.time_allocation.refresh_from_db()
        self.assertAlmostEqual(self.time_allocation.std_time_used, time_used)

    def test_with_one_obs_command_reports_dry_run_doesnt_modify_time(self):
        command_output = StringIO()
        command_err = StringIO()
        observation = self._add_observation(state='COMPLETED', time_completed=1000)
        # reset time used to 0 since creating the observation already modified it
        self.time_allocation.std_time_used = 0
        self.time_allocation.save()
        call_command('time_accounting', f'-p{self.proposal.id}', '-i1M0-SCICAM-SBIG', f'-s{self.semester.id}', '-d', stdout=command_output, stderr=command_err)
        time_used = (observation.configuration_statuses.first().summary.end - observation.configuration_statuses.first().summary.start).total_seconds() / 3600.0
        self.assertIn(f'Used {time_used} NORMAL hours, 0 RAPID_RESPONSE hours, and 0 TIME_CRITICAL hours', command_output.getvalue())
        self.assertIn('is different from existing', command_err.getvalue())
        self.time_allocation.refresh_from_db()
        self.assertEqual(self.time_allocation.std_time_used, 0)


class TestGetObservationsDetailAPIView(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.rg = create_simple_requestgroup(self.user, self.proposal)
        self.observation = mixer.blend(Observation, request=self.rg.requests.first())

        self.staff_user = blend_user(user_params={'is_staff': True, 'is_superuser': True}, profile_params={'staff_view': True})
        self.staff_proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.staff_proposal, user=self.staff_user)
        self.staff_rg = create_simple_requestgroup(self.staff_user, self.staff_proposal)
        self.staff_observation = mixer.blend(Observation, request=self.staff_rg.requests.first())

        self.public_proposal = mixer.blend(Proposal, public=True)
        mixer.blend(Membership, proposal=self.public_proposal, user=self.user)
        self.public_requestgroup = create_simple_requestgroup(self.user, self.public_proposal)
        self.public_observation = mixer.blend(Observation, request=self.public_requestgroup.requests.first())

    def test_unauthenticated_user_sees_only_public_observation(self):
        public_response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.public_observation.id}))
        self.assertEqual(public_response.status_code, 200)
        non_public_response = self.client.get(reverse('api:observations-detail', args=[self.observation.id]))
        self.assertEqual(non_public_response.status_code, 404)

    def test_authenticated_user_sees_their_observation_but_not_others(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 200)
        staff_response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.staff_observation.id}))
        self.assertEqual(staff_response.status_code, 404)

    def test_staff_user_with_staff_view_sees_others_observation(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 200)

    def test_staff_user_without_staff_view_doesnt_see_others_observation(self):
        self.staff_user.profile.staff_view = False
        self.staff_user.profile.save()
        response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.observation.id}))
        self.assertEqual(response.status_code, 404)

    def test_user_authored_only_enabled(self):
        user = blend_user(profile_params={'view_authored_requests_only': True})
        mixer.blend(Membership, proposal=self.public_proposal, user=user)
        requestgroup = create_simple_requestgroup(user, self.public_proposal)
        observation = mixer.blend(Observation, request=requestgroup.requests.first())
        self.client.force_login(user)
        response = self.client.get(reverse('api:observations-detail', kwargs={'pk': self.public_observation.id}))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('api:observations-detail', kwargs={'pk': observation.id}))
        self.assertEqual(response.status_code, 200)


class TestGetObservationsListAPIView(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.non_staff_user = blend_user()
        self.first_private_proposal = mixer.blend(Proposal, public=False)
        mixer.blend(Membership, proposal=self.first_private_proposal, user=self.non_staff_user)
        self.requestgroups = [
            self._generate_requestgroup(self.non_staff_user, self.first_private_proposal) for _ in range(3)
        ]
        self.observations = [
            self._generate_observation_data(
                requestgroup.requests.first().id,
                [requestgroup.requests.first().configurations.first().id]
            ) for requestgroup in self.requestgroups
        ]
        for observation in self.observations:
            self._create_observation(observation)

        self.public_proposal = mixer.blend(Proposal, public=True)
        mixer.blend(Membership, proposal=self.public_proposal, user=self.non_staff_user)
        self.public_requestgroups = [
            self._generate_requestgroup(self.non_staff_user, self.public_proposal) for _ in range(3)
        ]
        self.public_observations = [
            self._generate_observation_data(
                public_requestgroup.requests.first().id,
                [public_requestgroup.requests.first().configurations.first().id]
            ) for public_requestgroup in self.public_requestgroups
        ]
        for public_observation in self.public_observations:
            self._create_observation(public_observation)

        self.other_non_staff_user = blend_user()
        self.second_private_proposal = mixer.blend(Proposal, public=False)
        mixer.blend(Membership, proposal=self.second_private_proposal, user=self.other_non_staff_user)
        self.other_requestgroups = [
            self._generate_requestgroup(self.other_non_staff_user, self.second_private_proposal) for _ in range(3)
        ]
        self.other_observations = [
            self._generate_observation_data(
                other_requestgroup.requests.first().id,
                [other_requestgroup.requests.first().configurations.first().id]
            ) for other_requestgroup in self.other_requestgroups
        ]
        for other_observation in self.other_observations:
            self._create_observation(other_observation)

    def test_unauthenticated_user_only_sees_public_observations(self):
        self.client.logout()
        response = self.client.get(reverse('api:observations-list'))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.first_private_proposal.id, str(response.content))
        self.assertNotIn(self.second_private_proposal.id, str(response.content))

    def test_authenticated_user_sees_their_observations(self):
        self.client.force_login(self.non_staff_user)
        response = self.client.get(reverse('api:observations-list'))
        self.assertIn(self.first_private_proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.second_private_proposal.id, str(response.content))

    def test_staff_user_with_staff_view_sees_everything(self):
        staff_user = blend_user(user_params={'is_staff': True, 'is_superuser': True}, profile_params={'staff_view': True})
        self.client.force_login(staff_user)
        response = self.client.get(reverse('api:observations-list'))
        self.assertIn(self.first_private_proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertIn(self.second_private_proposal.id, str(response.content))

    def test_staff_user_without_staff_view_sees_only_their_observations(self):
        self.non_staff_user.is_staff = True
        self.non_staff_user.save()
        self.client.force_login(self.non_staff_user)
        response = self.client.get(reverse('api:observations-list'))
        self.assertIn(self.first_private_proposal.id, str(response.content))
        self.assertIn(self.public_proposal.id, str(response.content))
        self.assertNotIn(self.second_private_proposal.id, str(response.content))

    def test_user_with_authored_only(self):
        user = blend_user(profile_params={'view_authored_requests_only': True})
        mixer.blend(Membership, proposal=self.first_private_proposal, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse('api:observations-list'))
        self.assertNotIn(self.first_private_proposal.id, str(response.content))
        self.assertNotIn(self.public_proposal.id, str(response.content))

class TestGetObservationsFiltersApi(APITestCase):
    def setUp(self) -> None:
        super().setUp()

    def test_get_observations_filters(self):
        response = self.client.get(reverse('api:observations-filters'))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()['choice_fields'][0]['options']), 0)
        self.assertGreater(len(response.json()['fields']), 0)
