from django.utils import timezone
from django.test import TestCase
from mixer.backend.django import mixer
from datetime import datetime
from unittest.mock import patch

from observation_portal.requestgroups.request_utils import (get_airmasses_for_request_at_sites, get_telescope_states_for_request,
                                                 get_rise_set_intervals)
from observation_portal.requestgroups.models import (Request, Configuration, Target, RequestGroup, Window, Location,
                                                     Constraints, InstrumentConfig)
from observation_portal.proposals.models import Proposal, TimeAllocation, Semester
from observation_portal.common.test_telescope_states import TelescopeStatesFakeInput
from observation_portal.common.test_helpers import ConfigDBTestMixin, SetTimeMixin


class BaseSetupRequest(ConfigDBTestMixin, SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
                               end=datetime(2016, 12, 31, tzinfo=timezone.utc)
                               )
        self.time_allocation_1m0 = mixer.blend(TimeAllocation, proposal=self.proposal, semester=semester,
                                               telescope_class='1m0', std_allocation=100.0, std_time_used=0.0,
                                               too_allocation=10, too_time_used=0.0, ipp_limit=10.0,
                                               ipp_time_available=5.0, tc_time_available=10.0, tc_time_used=0.0)

        self.rg_single = mixer.blend(RequestGroup, proposal=self.proposal, operator='SINGLE')

        self.request = mixer.blend(Request, request_group=self.rg_single)

        self.configuration = mixer.blend(
            Configuration, request=self.request, instrument_name='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration, exposure_time=600, exposure_count=2,
            optical_elements={'filter': 'blah'}, bin_x=2, bin_y=2
        )

        mixer.blend(Window, request=self.request, start=datetime(2016, 10, 1, tzinfo=timezone.utc),
                    end=datetime(2016, 10, 8, tzinfo=timezone.utc))

        mixer.blend(Target, configuration=self.configuration, type='SIDEREAL', ra=22, dec=-33,
                    proper_motion_ra=0.0, proper_motion_dec=0.0)

        self.location = mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.blend(Constraints, request=self.request)


class TestRequestIntervals(BaseSetupRequest):
    def test_request_intervals_for_one_week(self):
        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = [(datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 1, 19, 13, 14, 944205, tzinfo=timezone.utc),
                            datetime(2016, 10, 2, 3, 19, 9, 181040, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 2, 19, 9, 19, 241762, tzinfo=timezone.utc),
                            datetime(2016, 10, 3, 3, 17, 47, 117329, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 3, 19, 5, 23, 539011, tzinfo=timezone.utc),
                            datetime(2016, 10, 4, 3, 16, 25, 202612, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 4, 19, 1, 27, 835928, tzinfo=timezone.utc),
                            datetime(2016, 10, 5, 3, 15, 3, 464340, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 5, 18, 57, 32, 132481, tzinfo=timezone.utc),
                            datetime(2016, 10, 6, 3, 12, 5, 895932, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 18, 53, 36, 428629, tzinfo=timezone.utc),
                            datetime(2016, 10, 7, 3, 8, 10, 183626, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 7, 18, 49, 40, 724307, tzinfo=timezone.utc),
                            datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc))]

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_removes_downtime(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = [(datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 1, 19, 13, 14, 944205, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 22, 0, 0, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 3, 0, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 3, 3, 17, 47, 117329, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 3, 19, 5, 23, 539011, tzinfo=timezone.utc),
                            datetime(2016, 10, 4, 3, 16, 25, 202612, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 4, 19, 1, 27, 835928, tzinfo=timezone.utc),
                            datetime(2016, 10, 5, 3, 15, 3, 464340, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 5, 18, 57, 32, 132481, tzinfo=timezone.utc),
                            datetime(2016, 10, 6, 3, 12, 5, 895932, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 18, 53, 36, 428629, tzinfo=timezone.utc),
                            datetime(2016, 10, 7, 3, 8, 10, 183626, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 7, 18, 49, 40, 724307, tzinfo=timezone.utc),
                            datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc))]

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_removes_lots_of_downtime(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-07T12:00:00Z',
                                       'end': '2017-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-07T12:00:00Z',
                                       'end': '2017-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T12:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T12:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      ]

        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = [(datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 1, 19, 13, 14, 944205, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 22, 0, 0, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 0, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 6, 3, 12, 5, 895932, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 18, 53, 36, 428629, tzinfo=timezone.utc),
                            datetime(2016, 10, 7, 3, 8, 10, 183626, tzinfo=timezone.utc))]

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_all_downtime(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-11-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-11-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = []

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_downtime_out_of_range(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-10-01T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-10-01T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-08T00:00:00Z',
                                       'end': '2016-11-01T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-08T00:00:00Z',
                                       'end': '2016-11-01T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = [(datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 1, 19, 13, 14, 944205, tzinfo=timezone.utc),
                            datetime(2016, 10, 2, 3, 19, 9, 181040, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 2, 19, 9, 19, 241762, tzinfo=timezone.utc),
                            datetime(2016, 10, 3, 3, 17, 47, 117329, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 3, 19, 5, 23, 539011, tzinfo=timezone.utc),
                            datetime(2016, 10, 4, 3, 16, 25, 202612, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 4, 19, 1, 27, 835928, tzinfo=timezone.utc),
                            datetime(2016, 10, 5, 3, 15, 3, 464340, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 5, 18, 57, 32, 132481, tzinfo=timezone.utc),
                            datetime(2016, 10, 6, 3, 12, 5, 895932, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 18, 53, 36, 428629, tzinfo=timezone.utc),
                            datetime(2016, 10, 7, 3, 8, 10, 183626, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 7, 18, 49, 40, 724307, tzinfo=timezone.utc),
                            datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc))]

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_overlapping_downtime(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-04T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-04T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'observatory': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_rise_set_intervals(self.request.as_dict)

        truth_intervals = [(datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 1, 19, 13, 14, 944205, tzinfo=timezone.utc),
                            datetime(2016, 10, 1, 22, 0, 0, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 0, 0, 0, tzinfo=timezone.utc),
                            datetime(2016, 10, 6, 3, 12, 5, 895932, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 6, 18, 53, 36, 428629, tzinfo=timezone.utc),
                            datetime(2016, 10, 7, 3, 8, 10, 183626, tzinfo=timezone.utc)),
                           (datetime(2016, 10, 7, 18, 49, 40, 724307, tzinfo=timezone.utc),
                            datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc))]

        self.assertEqual(intervals, truth_intervals)


class TestRequestAirmass(BaseSetupRequest):
    def test_airmass_calculation(self):
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict)

        # Should be no data betwee 3:30AM and 18:30PM acording to pure rise set for this target, so verify that
        expected_null_range = (datetime(2016, 10, 1, 3, 30, 0), datetime(2016, 10, 1, 18, 30, 0))

        for airmass_time in airmasses['airmass_data']['tst']['times']:
            atime = datetime.strptime(airmass_time, '%Y-%m-%dT%H:%M')
            if atime > expected_null_range[0] and atime < expected_null_range[1]:
                self.fail("Should not get airmass ({}) within range {}".format(atime, expected_null_range))

    def test_airmass_calculation_empty(self):
        self.location.site = 'cpt'
        self.location.save()
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict)

        self.assertFalse(airmasses['airmass_data'])


class TestRequestTelescopeStates(TelescopeStatesFakeInput):
    def setUp(self):
        super().setUp()
        self.time_patcher = patch('observation_portal.requestgroups.serializers.timezone.now')
        self.mock_now = self.time_patcher.start()
        self.mock_now.return_value = datetime(2016, 10, 1, tzinfo=timezone.utc)
        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
                               end=datetime(2016, 12, 31, tzinfo=timezone.utc)
                               )
        self.time_allocation_1m0 = mixer.blend(TimeAllocation, proposal=self.proposal, semester=semester,
                                               telescope_class='1m0', std_allocation=100.0, std_time_used=0.0,
                                               too_allocation=10, too_time_used=0.0, ipp_limit=10.0,
                                               ipp_time_available=5.0, tc_time_available=10.0, tc_time_used=0.0)

        self.rg_single = mixer.blend(RequestGroup, proposal=self.proposal, operator='SINGLE')

        self.request = mixer.blend(Request, request_group=self.rg_single)

        self.configuration = mixer.blend(
            Configuration, request=self.request, instrument_name='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration, exposure_time=600, exposure_count=2,
            optical_elements={'filter': 'blah'}, bin_x=2, bin_y=2
        )

        mixer.blend(Window, request=self.request, start=datetime(2016, 10, 1, tzinfo=timezone.utc),
                    end=datetime(2016, 10, 2, tzinfo=timezone.utc))

        mixer.blend(Target, configuration=self.configuration, type='SIDEREAL', ra=22, dec=-33,
                    proper_motion_ra=0.0, proper_motion_dec=0.0)

        self.location = mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.blend(Constraints, configuration=self.configuration, max_airmass=2.0)

    def tearDown(self):
        super().tearDown()
        self.time_patcher.stop()

        # super(BaseSetupRequest, self).tearDown()

    def test_telescope_states_calculation(self):
        telescope_states = get_telescope_states_for_request(self.request)
        # Assert that telescope states were received for this request
        self.assertIn(self.tk1, telescope_states)
        self.assertIn(self.tk2, telescope_states)

        expected_start_of_night = datetime(2016, 10, 1, 18, 45, 2, 760910, tzinfo=timezone.utc)

        # These are the same states tested for similar times in the telescope_states test class
        doma_expected_available_state = {'telescope': 'tst.doma.1m0a',
                                         'event_type': 'AVAILABLE',
                                         'event_reason': 'Available for scheduling',
                                         'start': expected_start_of_night,
                                         'end': datetime(2016, 10, 1, 20, 44, 58, tzinfo=timezone.utc)
                                         }

        self.assertIn(doma_expected_available_state, telescope_states[self.tk1])

        domb_expected_available_state1 = {'telescope': 'tst.domb.1m0a',
                                          'event_type': 'AVAILABLE',
                                          'event_reason': 'Available for scheduling',
                                          'start': expected_start_of_night,
                                          'end': datetime(2016, 10, 1, 19, 24, 59, tzinfo=timezone.utc)
                                          }

        self.assertIn(domb_expected_available_state1, telescope_states[self.tk2])

        domb_expected_available_state2 = {'telescope': 'tst.domb.1m0a',
                                          'event_type': 'AVAILABLE',
                                          'event_reason': 'Available for scheduling',
                                          'start': datetime(2016, 10, 1, 20, 24, 59, tzinfo=timezone.utc),
                                          'end': datetime(2016, 10, 1, 20, 44, 58, tzinfo=timezone.utc)
                                          }

        self.assertIn(domb_expected_available_state2, telescope_states[self.tk2])

    def test_telescope_states_empty(self):
        self.location.site = 'cpt'
        self.location.save()
        telescope_states = get_telescope_states_for_request(self.request)

        self.assertEqual({}, telescope_states)
