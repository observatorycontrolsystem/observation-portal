from rest_framework.test import APITestCase
from observation_portal.common.test_helpers import ConfigDBTestMixin, SetTimeMixin
from django.utils import timezone
from mixer.backend.django import mixer
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.urls import reverse

from observation_portal.requestgroups.models import (RequestGroup, Request, DraftRequestGroup, Window, Target,
                                                     Configuration, Location, Constraints, InstrumentConfig,
                                                     AcquisitionConfig, GuidingConfig)
from observation_portal.proposals.models import Proposal, Membership, TimeAllocation, Semester
from observation_portal.accounts.models import Profile
import copy

import logging

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
                "instrument_name": "1M0-SCICAM-SBIG",
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
    "ipp_value": 1.05,
    "site": "tst",
    "observatory": "doma",
    "telescope": "1m0a",
    "start": "2016-09-05T22:35:39Z",
    "end": "2016-09-05T23:35:40Z"
}


class TestPostObservationApi(ConfigDBTestMixin, SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
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

    def test_post_observation_not_admin(self):
        self.other_user = mixer.blend(User)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('api:observations-list'), data=self.observation)
        self.assertEqual(response.status_code, 403)

    def test_post_observation_unauthenticated(self):
        self.other_user = mixer.blend(User, is_staff=True)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('api:observations-list'), data=self.observation)
        self.assertEqual(response.status_code, 400)

    def test_post_observation_authenticated(self):
        response = self.client.post(reverse('api:observations-list'), data=self.observation)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], self.observation['name'])

