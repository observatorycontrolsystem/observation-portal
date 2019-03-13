from rest_framework.test import APITestCase
from observation_portal.common.test_helpers import SetTimeMixin
from django.utils import timezone
from mixer.backend.django import mixer
from django.contrib.auth.models import User
from datetime import datetime
from dateutil.parser import parse
from django.urls import reverse

from observation_portal.requestgroups.models import RequestGroup, Window, Location
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.proposals.models import Proposal, Membership, Semester
from observation_portal.accounts.models import Profile
from observation_portal.common.test_helpers import create_simple_requestgroup, create_simple_configuration
import observation_portal.observations.signals.handlers  # noqa


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
                        "rot_mode": "",
                        "extra_params": {}
                    }
                ],
                "acquisition_config": {
                    "mode": "OFF",
                    "extra_params": {}
                },
                "guiding_config": {
                    "state": "OFF",
                    "mode": "",
                    "optical_elements": {},
                    "exposure_time": 10.0,
                    "extra_params": {}
                },
                "target": {
                    "parallax": 0.0,
                    "equinox": "J2000",
                    "coordinate_system": "ICRS",
                    "proper_motion_ra": 0.0,
                    "ra": 83.3833402357991,
                    "type": "SIDEREAL",
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
        self.other_user = mixer.blend(User)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 403)

    def test_post_observation_user_not_on_proposal(self):
        self.other_user = mixer.blend(User, is_staff=True)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('do not belong to the proposal', str(response.content))

    def test_post_observation_authenticated(self):
        response = self.client.post(reverse('api:schedule-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], self.observation['name'])

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
        bad_observation['start'] = "2014-09-05T22:35:39Z"
        response = self.client.post(reverse('api:schedule-list'), data=bad_observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('start', response.json())
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
        bad_observation['request']['configurations'][0]['guiding_config']['state'] = 'ON'
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
        observation['request']['configurations'][0]['guiding_config']['state'] = 'ON'
        observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
        del observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        self.assertEqual(response.status_code, 201)

    def test_post_observation_no_guide_camera_sets_default(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        observation['request']['configurations'][0]['guiding_config']['state'] = 'ON'
        observation['request']['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        observation['request']['configurations'][0]['type'] = 'NRES_SPECTRUM'
        del observation['request']['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']

        response = self.client.post(reverse('api:schedule-list'), data=observation)
        obs_json = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(obs_json['request']['configurations'][0]['guide_camera_name'], 'ak02')

    def test_self_guiding_with_no_guide_camera_set_sets_same_instrument_for_guide_camera(self):
        observation = copy.deepcopy(self.observation)
        observation['request']['configurations'][0]['guiding_config']['state'] = 'ON'
        observation['request']['configurations'][0]['extra_params']['self_guide'] = True
        response = self.client.post(reverse('api:schedule-list'), data=observation)
        obs_json = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            obs_json['request']['configurations'][0]['instrument_name'],
            obs_json['request']['configurations'][0]['guide_camera_name']
        )


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
        self.observation['request']['configurations'][2]['guiding_config']['state'] = 'ON'
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
        self.proposal = mixer.blend(Proposal, direct_submission=True)
        self.user = mixer.blend(User, is_admin=True, is_superuser=True, is_staff=True)
        mixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.window = mixer.blend(
            Window, start=datetime(2016, 9, 3, tzinfo=timezone.utc), end=datetime(2016, 9, 6, tzinfo=timezone.utc)
        )
        self.location = mixer.blend(Location, telescope_class='1m0')
        self.requestgroup = create_simple_requestgroup(self.user, self.proposal, window=self.window, location=self.location)
        self.requestgroup.observation_type = RequestGroup.NORMAL
        self.requestgroup.save()
        configuration = self.requestgroup.requests.first().configurations.first()
        configuration.instrument_type = '1M0-SCICAM-SBIG'
        configuration.save()

    def _generate_observation_data(self, request_id, configuration_id_list, guide_camera_name='xx03'):
        observation = {
            "request": request_id,
            "site": "tst",
            "enclosure": "domb",
            "telescope": "1m0a",
            "start": "2016-09-05T22:35:39Z",
            "end": "2016-09-05T23:35:40Z",
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
        self.assertIn('The start and end times do not fall within any window of the request', str(response.content))

    def test_observation_not_in_a_request_window_but_overlaps_with_window_end_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-05T23:50:00Z"
        observation['end'] = "2016-09-06T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The start and end times do not fall within any window of the request', str(response.content))

    def test_observation_starting_after_request_window_end_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-06T23:50:00Z"
        observation['end'] = "2016-09-07T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The start and end times do not fall within any window of the request', str(response.content))

    def test_observation_ending_before_request_window_start_rejected(self):
        observation = self._generate_observation_data(
            self.requestgroup.requests.first().id, [self.requestgroup.requests.first().configurations.first().id]
        )
        observation['start'] = "2016-09-02T00:00:00Z"
        observation['end'] = "2016-09-02T00:30:00Z"
        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The start and end times do not fall within any window of the request', str(response.content))

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
