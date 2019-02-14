from rest_framework.test import APITestCase
from observation_portal.common.test_helpers import SetTimeMixin
from django.utils import timezone
from mixer.backend.django import mixer
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.urls import reverse

from observation_portal.requestgroups.models import (RequestGroup, Request, DraftRequestGroup, Window, Target,
                                                     Configuration, Location, Constraints, InstrumentConfig,
                                                     AcquisitionConfig, GuidingConfig)
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.proposals.models import Proposal, Membership, TimeAllocation, Semester
from observation_portal.accounts.models import Profile
from observation_portal.common.test_helpers import create_simple_requestgroup

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
                    "name": "",
                    "mode": "OFF",
                    "extra_params": {}
                },
                "guiding_config": {
                    "name": "",
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


class TestPostObservationApi(SetTimeMixin, APITestCase):
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

        self.requestgroup = create_simple_requestgroup(self.user, self.proposal)
        self.requestgroup.requests.all()[0].configurations.all()[0].instrument_type = '1M0-SCICAM-SBIG'
        self.requestgroup.requests.all()[0].configurations.all()[0].save()

    def test_observation_with_valid_instrument_name_succeeds(self):
        observation = {
            "request": self.requestgroup.requests.all()[0].id,
            "site": "tst",
            "enclosure": "domb",
            "telescope": "1m0a",
            "start": "2016-09-05T22:35:39Z",
            "end": "2016-09-05T23:35:40Z",
            "configuration_statuses": [
                {
                    "configuration": self.requestgroup.requests.all()[0].configurations.all()[0].id,
                    "instrument_name": "xx03",
                    "guide_camera_name": "xx03"
                }
            ]
        }

        response = self.client.post(reverse('api:observations-list'), data=observation)
        self.assertEqual(response.status_code, 201)
