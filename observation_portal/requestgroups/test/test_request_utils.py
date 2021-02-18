from django.utils import timezone
from django.test import TestCase
from mixer.backend.django import mixer
from datetime import datetime
from copy import deepcopy
from unittest.mock import patch

from time_intervals.intervals import Intervals

from observation_portal.requestgroups.request_utils import (get_airmasses_for_request_at_sites, get_telescope_states_for_request,
                                                            get_filtered_rise_set_intervals_by_site)
from observation_portal.requestgroups.models import (Request, Configuration, Target, RequestGroup, Window, Location,
                                                     Constraints, InstrumentConfig, AcquisitionConfig, GuidingConfig)
from observation_portal.proposals.models import Proposal, TimeAllocation, Semester
from observation_portal.common.test_telescope_states import TelescopeStatesFakeInput
from observation_portal.common.test_helpers import SetTimeMixin


class BaseSetupRequest(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0, tc_time_available=10.0,
            tc_time_used=0.0
        )
        self.rg_single = mixer.blend(RequestGroup, proposal=self.proposal, operator='SINGLE',
                                     observation_type=RequestGroup.NORMAL)
        self.request = mixer.blend(Request, request_group=self.rg_single)
        self.configuration = mixer.blend(
            Configuration, request=self.request, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration, exposure_time=600, exposure_count=2,
            optical_elements={'filter': 'blah'}, bin_x=2, bin_y=2
        )
        self.acquisition_config = mixer.blend(AcquisitionConfig, configuration=self.configuration)
        self.guiding_config = mixer.blend(GuidingConfig, configuration=self.configuration)
        mixer.blend(
            Window, request=self.request, start=datetime(2016, 10, 1, tzinfo=timezone.utc),
            end=datetime(2016, 10, 8, tzinfo=timezone.utc)
        )
        mixer.blend(
            Target, configuration=self.configuration, type='ICRS', ra=22, dec=-33, proper_motion_ra=0.0,
            proper_motion_dec=0.0
        )
        self.location = mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.blend(Constraints, configuration=self.configuration)


class TestRequestIntervals(BaseSetupRequest):
    def test_request_intervals_for_one_week(self):
        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

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

    def test_request_intervals_for_staff_at_location(self):
        request_dict = self.request.as_dict()
        request_dict['location']['site'] = 'tst'
        request_dict['location']['enclosure'] = 'domd'
        request_dict['location']['telescope'] = '1m0a'
        request_dict['configurations'][0]['instrument_type'] = '1M0-SCICAM-SBAG'
        intervals = get_filtered_rise_set_intervals_by_site(request_dict, is_staff=False).get('tst', [])
        self.assertEqual(intervals, [])
        intervals = get_filtered_rise_set_intervals_by_site(request_dict, is_staff=True).get('tst', [])
        self.assertNotEqual(intervals, [])

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_removes_downtime(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

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
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-07T12:00:00Z',
                                       'end': '2017-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-07T12:00:00Z',
                                       'end': '2017-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T12:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T12:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      ]

        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

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
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-11-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

        truth_intervals = []

        self.assertEqual(intervals, truth_intervals)

    @patch('observation_portal.common.downtimedb.DowntimeDB._get_downtime_data')
    def test_request_intervals_for_one_week_downtime_out_of_range(self, downtime_data):
        downtime_data.return_value = [{'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-10-01T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-09-01T22:00:00Z',
                                       'end': '2016-10-01T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-08T00:00:00Z',
                                       'end': '2016-11-01T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-08T00:00:00Z',
                                       'end': '2016-11-01T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

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
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-01T22:00:00Z',
                                       'end': '2016-10-04T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-03T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'doma',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'},
                                      {'start': '2016-10-02T00:00:00Z',
                                       'end': '2016-10-06T00:00:00Z',
                                       'site': 'tst',
                                       'enclosure': 'domb',
                                       'telescope': '1m0a',
                                       'reason': 'Whatever'}
                                      ]

        intervals = get_filtered_rise_set_intervals_by_site(self.request.as_dict()).get('tst', [])

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


class TestMultipleTargetRequestIntervals(BaseSetupRequest):
    def test_request_intervals_for_multiple_targets_intersected(self):
        request_dict = self.request.as_dict()
        intervals = get_filtered_rise_set_intervals_by_site(request_dict).get('tst', [])
        truth_intervals = [
            (datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
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
            datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc))
        ]

        self.assertEqual(intervals, truth_intervals)
        # now create get the intervals for a request with the second target
        configuration2 = deepcopy(request_dict['configurations'][0])
        configuration2['target']['ra'] = 85.0  # change the RA so the target has different visibility
        request_dict2 = deepcopy(request_dict)
        request_dict2['configurations'][0] = configuration2
        intervals2 = get_filtered_rise_set_intervals_by_site(request_dict2).get('tst', [])
        truth_intervals2 = [
            (datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc), datetime(2016, 10, 1, 3, 20, 31, 366820, tzinfo=timezone.utc)),
            (datetime(2016, 10, 1, 23, 24, 4, 392218, tzinfo=timezone.utc), datetime(2016, 10, 2, 3, 19, 9, 181040, tzinfo=timezone.utc)),
            (datetime(2016, 10, 2, 23, 20, 8, 717423, tzinfo=timezone.utc), datetime(2016, 10, 3, 3, 17, 47, 117329, tzinfo=timezone.utc)),
            (datetime(2016, 10, 3, 23, 16, 13, 42308, tzinfo=timezone.utc), datetime(2016, 10, 4, 3, 16, 25, 202612, tzinfo=timezone.utc)),
            (datetime(2016, 10, 4, 23, 12, 17, 366627, tzinfo=timezone.utc), datetime(2016, 10, 5, 3, 15, 3, 464340, tzinfo=timezone.utc)),
            (datetime(2016, 10, 5, 23, 8, 21, 690204, tzinfo=timezone.utc), datetime(2016, 10, 6, 3, 13, 41, 930536, tzinfo=timezone.utc)),
            (datetime(2016, 10, 6, 23, 4, 26, 12943, tzinfo=timezone.utc), datetime(2016, 10, 7, 3, 12, 20, 629833, tzinfo=timezone.utc)),
            (datetime(2016, 10, 7, 23, 0, 30, 334810, tzinfo=timezone.utc), datetime(2016, 10, 8, 0, 0, tzinfo=timezone.utc)),
        ]
        self.assertEqual(intervals2, truth_intervals2)

        # now get the intervals for both targets combined in the request and verify they are intersected
        request_dict3 = deepcopy(request_dict)
        request_dict3['configurations'].append(configuration2)
        intervals3 = get_filtered_rise_set_intervals_by_site(request_dict3).get('tst', [])
        truth_intervals_combined = Intervals(truth_intervals).intersect([Intervals(truth_intervals2)]).toTupleList()
        self.assertEqual(intervals3, truth_intervals_combined)

    def test_request_intervals_for_multiple_targets_empty_if_one_is_empty(self):
        request_dict = self.request.as_dict()

        # now create get the intervals for a request with the second target that isn't visible
        configuration2 = deepcopy(request_dict['configurations'][0])
        configuration2['target']['dec'] = 70.0  # change the DEC so the target isn't visible
        request_dict2 = deepcopy(request_dict)
        request_dict2['configurations'][0] = configuration2
        intervals = get_filtered_rise_set_intervals_by_site(request_dict2).get('tst', [])
        truth_intervals = [
        ]
        self.assertEqual(intervals, truth_intervals)

        # now get the intervals for both targets combined in the request and verify they are intersected and empty
        request_dict3 = deepcopy(request_dict)
        request_dict3['configurations'].append(configuration2)
        intervals3 = get_filtered_rise_set_intervals_by_site(request_dict3).get('tst', [])
        self.assertEqual(intervals3, [])

    def test_airmass_for_multiple_targets_averaged(self):
        request_dict = self.request.as_dict()
        airmasses = get_airmasses_for_request_at_sites(request_dict)

        # now create get the intervals for a request with the second target
        configuration2 = deepcopy(request_dict['configurations'][0])
        configuration2['target']['ra'] = 85.0  # change the RA so the target has different visibility
        request_dict2 = deepcopy(request_dict)
        request_dict2['configurations'][0] = configuration2
        airmasses2 = get_airmasses_for_request_at_sites(request_dict2)

        # now get the intervals for both targets combined in the request and verify they are intersected
        request_dict3 = deepcopy(request_dict)
        request_dict3['configurations'].append(configuration2)
        airmasses_combined = get_airmasses_for_request_at_sites(request_dict3)

        # The first few intervals should at least match up in time, so compare those
        for i in range(4):
            self.assertNotEqual(airmasses['airmass_data']['tst']['airmasses'][i], airmasses2['airmass_data']['tst']['airmasses'][i])
            average_airmass = (airmasses['airmass_data']['tst']['airmasses'][i] +  airmasses2['airmass_data']['tst']['airmasses'][i]) / 2.0
            self.assertEqual(average_airmass, airmasses_combined['airmass_data']['tst']['airmasses'][i])
        average_airmass_limit = (airmasses['airmass_limit'] + airmasses2['airmass_limit']) / 2.0
        self.assertEqual(average_airmass_limit, airmasses_combined['airmass_limit'])


class TestRequestAirmass(BaseSetupRequest):
    def test_airmass_calculation(self):
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict())

        # Should be no data betwee 3:30AM and 18:30PM acording to pure rise set for this target, so verify that
        expected_null_range = (datetime(2016, 10, 1, 3, 30, 0), datetime(2016, 10, 1, 18, 30, 0))

        for airmass_time in airmasses['airmass_data']['tst']['times']:
            atime = datetime.strptime(airmass_time, '%Y-%m-%dT%H:%M')
            if atime > expected_null_range[0] and atime < expected_null_range[1]:
                self.fail("Should not get airmass ({}) within range {}".format(atime, expected_null_range))

    def test_airmass_calculation_empty(self):
        self.location.site = 'cpt'
        self.location.save()
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict())

        self.assertFalse(airmasses['airmass_data'])

    def test_satellite_target_types_airmass_calc_is_empty(self):
        self.configuration.target.type = 'SATELLITE'
        self.configuration.target.altitude = 90
        self.configuration.target.azimuth = 0
        self.configuration.target.diff_altitude_rate = 0.01
        self.configuration.target.diff_azimuth_rate = 0.01
        self.configuration.target.diff_epoch = 15000
        self.configuration.target.diff_altitude_acceleration = 0.001
        self.configuration.target.diff_azimuth_acceleration = 0.001
        self.configuration.target.save()
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict())
        self.assertFalse(airmasses['airmass_data'])

    def test_hour_angle_target_types_airmass_calc_is_empty(self):
        self.configuration.target.type = 'HOUR_ANGLE'
        self.configuration.target.hour_angle = 0
        self.configuration.target.save()
        airmasses = get_airmasses_for_request_at_sites(self.request.as_dict())
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
                                               rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
                                               ipp_time_available=5.0, tc_time_available=10.0, tc_time_used=0.0)

        self.rg_single = mixer.blend(RequestGroup, proposal=self.proposal, operator='SINGLE',
                                     observation_type=RequestGroup.NORMAL)

        self.request = mixer.blend(Request, request_group=self.rg_single)

        self.configuration = mixer.blend(
            Configuration, request=self.request, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration, exposure_time=600, exposure_count=2,
            optical_elements={'filter': 'blah'}, bin_x=2, bin_y=2
        )
        self.acquisition_config = mixer.blend(AcquisitionConfig, configuration=self.configuration)
        self.guiding_config = mixer.blend(GuidingConfig, configuration=self.configuration)

        mixer.blend(Window, request=self.request, start=datetime(2016, 10, 1, tzinfo=timezone.utc),
                    end=datetime(2016, 10, 2, tzinfo=timezone.utc))

        mixer.blend(Target, configuration=self.configuration, type='ICRS', ra=22, dec=-33,
                    proper_motion_ra=0.0, proper_motion_dec=0.0)

        self.location = mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.blend(Constraints, configuration=self.configuration, max_airmass=2.0)

    def tearDown(self):
        super().tearDown()
        self.time_patcher.stop()

        # super(BaseSetupRequest, self).tearDown()

    def test_telescope_states_calculation(self):
        telescope_states = get_telescope_states_for_request(self.request.as_dict())
        # Assert that telescope states were received for this request
        self.assertIn(self.tk1, telescope_states)
        self.assertIn(self.tk2, telescope_states)

        expected_start_of_night = datetime(2016, 10, 1, 18, 45, 49, 461652, tzinfo=timezone.utc)

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

    def test_telescope_states_calculation_with_no_target(self):
        request_dict = self.request.as_dict()
        request_dict['configurations'][0]['target'] = {}

        telescope_states = get_telescope_states_for_request(request_dict)
        # Assert that telescope states were received for this request
        self.assertIn(self.tk1, telescope_states)
        self.assertIn(self.tk2, telescope_states)

        expected_start_of_night_doma = datetime(2016, 10, 1, 18, 24, 58, tzinfo=timezone.utc)
        expected_start_of_night_domb = datetime(2016, 10, 1, 18, 30, 0, tzinfo=timezone.utc)


        # These are the same states tested for similar times in the telescope_states test class
        doma_expected_available_state = {'telescope': 'tst.doma.1m0a',
                                         'event_type': 'AVAILABLE',
                                         'event_reason': 'Available for scheduling',
                                         'start': expected_start_of_night_doma,
                                         'end': datetime(2016, 10, 1, 20, 44, 58, tzinfo=timezone.utc)
                                         }

        self.assertIn(doma_expected_available_state, telescope_states[self.tk1])

        domb_expected_available_state1 = {'telescope': 'tst.domb.1m0a',
                                          'event_type': 'AVAILABLE',
                                          'event_reason': 'Available for scheduling',
                                          'start': expected_start_of_night_domb,
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
        telescope_states = get_telescope_states_for_request(self.request.as_dict())

        self.assertEqual({}, telescope_states)
