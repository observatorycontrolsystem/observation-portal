from django.test import TestCase
from mixer.backend.django import mixer
from django.utils import timezone
import datetime

from observation_portal.common.test_helpers import SetTimeMixin
from observation_portal.requestgroups.cadence import expand_cadence_request
from observation_portal.requestgroups.models import (
    RequestGroup, Request, Configuration, Target, Constraints, Location, InstrumentConfig, AcquisitionConfig,
    GuidingConfig
)


class TestCadence(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.req_group = mixer.blend(RequestGroup, observation_type=RequestGroup.NORMAL)
        self.req = mixer.blend(Request, request_group=self.req_group)
        self.configuration = mixer.blend(
            Configuration, request=self.req, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration, exposure_time=10, exposure_count=1,
            optical_elements={'filter': 'blah'}, bin_x=2, bin_y=2
        )
        self.acquisition_config = mixer.blend(AcquisitionConfig, configuration=self.configuration)
        self.guiding_config = mixer.blend(GuidingConfig, configuration=self.configuration)
        mixer.blend(
            Target, configuration=self.configuration, type='ICRS', ra=34.4, dec=20, proper_motion_ra=0.0,
            proper_motion_dec=0.0
        )
        mixer.blend(Constraints, configuration=self.configuration, max_airmass=2.0)
        mixer.blend(Location, request=self.req, telecope_class='1m0')

    def test_correct_number_of_requests_small_cadence(self):
        r_dict = self.req.as_dict()
        r_dict['cadence'] = {
            'start': datetime.datetime(2016, 9, 1, tzinfo=timezone.utc),
            'end': datetime.datetime(2016, 9, 3, tzinfo=timezone.utc),
            'period': 24.0,
            'jitter': 12.0
        }
        requests = expand_cadence_request(r_dict)
        self.assertEqual(len(requests), 2)

    def test_correct_number_of_requests_large_cadence(self):
        r_dict = self.req.as_dict()
        r_dict['cadence'] = {
            'start': datetime.datetime(2016, 9, 1, tzinfo=timezone.utc),
            'end': datetime.datetime(2016, 10, 1, tzinfo=timezone.utc),
            'period': 24.0,
            'jitter': 12.0
        }
        requests = expand_cadence_request(r_dict)
        self.assertEqual(len(requests), 26)

    def test_correct_number_of_requests_bounded_window(self):
        r_dict = self.req.as_dict()
        r_dict['cadence'] = {
            'start': datetime.datetime(2016, 9, 1, tzinfo=timezone.utc),
            'end': datetime.datetime(2016, 9, 2, tzinfo=timezone.utc),
            'period': 24.0,
            'jitter': 12.0
        }
        requests = expand_cadence_request(r_dict)
        self.assertEqual(len(requests), 1)

    def test_correct_number_of_requests_overlapping_windows(self):
        r_dict = self.req.as_dict()
        r_dict['cadence'] = {
            'start': datetime.datetime(2016, 9, 1, tzinfo=timezone.utc),
            'end': datetime.datetime(2016, 9, 2, tzinfo=timezone.utc),
            'period': 1.0,
            'jitter': 2.0
        }
        requests = expand_cadence_request(r_dict)
        self.assertEqual(len(requests), 5)
