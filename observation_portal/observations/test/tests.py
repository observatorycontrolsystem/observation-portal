from datetime import datetime, timedelta
from io import StringIO

from rest_framework.test import APITestCase
from django.utils import timezone
from mixer.backend.django import mixer
from django.contrib.auth.models import User
from dateutil.parser import parse
from django.urls import reverse
from django.core import cache
from django.core.management import call_command

from observation_portal.common.test_helpers import SetTimeMixin
from observation_portal.requestgroups.models import RequestGroup, Window, Location, Request
from observation_portal.observations.time_accounting import configuration_time_used
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.proposals.models import Proposal, Membership, Semester, TimeAllocation
from observation_portal.accounts.models import Profile
from observation_portal.common.test_helpers import create_simple_requestgroup, create_simple_configuration
from observation_portal.accounts.test_utils import blend_user
from observation_portal.observations import views
from observation_portal.observations import viewsets
import observation_portal.observations.signals.handlers  # noqa

from unittest.mock import patch
import copy

observation = {
    "request": {
        "configurations": [
            {
                "constraints": {
                    "max_airmass": 2.0,
                    "min_lunar_distance": 30.0,
                },
                "instrument_configs": [
                    {
                        "optical_elements": {
                            "filter": "air"
                        },
                        "mode": "",
                        "exposure_time": 370.0,
                        "exposure_count": 1,
                        "bin_x": 1,
                        "bin_y": 1,
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
        self.user = mixer.blend(User, is_admin=True, is_superuser=True, is_staff=True)
        mixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )

        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.observation = copy.deepcopy(observation)
        self.observation['proposal'] = self.proposal.id

    def test_post_observation_user_not_logged_in(self):
        other_user = mixer.blend(User)
        self.client.force_login(other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 403)

    def test_post_observation_user_not_on_proposal(self):
        other_user = mixer.blend(User, is_staff=True)
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
        del observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)

    def test_post_observation_no_guide_camera_sets_default(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        observation['request']['configurations'][0]['guiding_config']['mode'] = 'ON'
        observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
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
        self.user = mixer.blend(User, is_admin=True, is_superuser=True, is_staff=True)
        mixer.blend(Profile, user=self.user)
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


class TestObservationApiBase(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, direct_submission=False)
        self.user = mixer.blend(User, is_admin=True, is_superuser=True, is_staff=True)
        mixer.blend(Profile, user=self.user)
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
        rr_requestgroup = create_simple_requestgroup(self.user, self.proposal, window=self.window, location=self.location)
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
        # Mock the cache with a real one for these tests
        self.locmem_cache = cache._create_cache('django.core.cache.backends.locmem.LocMemCache')
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

    def test_last_schedule_date_is_not_updated_when_observation_is_mixed(self):
        mixer.blend(Observation, request=self.requestgroup.requests.first())
        last_schedule_cached = self.locmem_cache.get('observation_portal_last_schedule_time_tst')
        self.assertIsNone(last_schedule_cached)
        response = self.client.get(reverse('api:last_scheduled'))
        last_schedule = response.json()['last_schedule_time']
        self.assertAlmostEqual(parse(last_schedule), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))


class TestTimeAccounting(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.time_allocation = mixer.blend(TimeAllocation, instrument_type='1M0-SCICAM-SBIG', semester=self.semester,
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

        return config_status, summary

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

    def test_multiple_requests_leads_to_consistent_time_accounting(self):
        self._helper_test_summary_save(
            observation_type=RequestGroup.NORMAL,
            config_status_state='COMPLETED',
            config_end=datetime(2019, 9, 5, 22, 58, 24, tzinfo=timezone.utc)
        )
        self.time_allocation.refresh_from_db()
        time_used = self.time_allocation.std_time_used

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
        time_used += (config_end - config_start).total_seconds() / 3600.0
        self.assertAlmostEqual(self.time_allocation.std_time_used, time_used, 5)


class TestTimeAccountingCommand(TestObservationApiBase):
    def setUp(self):
        super().setUp()
        self.time_allocation = mixer.blend(TimeAllocation, instrument_type='1M0-SCICAM-SBIG', semester=self.semester,
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
