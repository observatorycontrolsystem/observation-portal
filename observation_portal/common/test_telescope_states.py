from observation_portal.common.telescope_states import (TelescopeStates, get_telescope_availability_per_day,
                                              combine_telescope_availabilities_by_site_and_class)
from observation_portal.common.configdb import TelescopeKey
from observation_portal.common import rise_set_utils

from time_intervals.intervals import Intervals
from django.test import TestCase
from datetime import datetime, timedelta
from django.utils import timezone
from unittest.mock import patch
import json


class TelescopeStatesFakeInput(TestCase):
    def setUp(self):
        super().setUp()
        self.es_output = [
            {
                '_source': {
                    'timestamp': '2016-10-01 18:24:58',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "",
                    'observatory': 'doma',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 19:24:58',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "",
                    'observatory': 'doma',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 20:24:58',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "",
                    'observatory': 'doma',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 20:44:58',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "Site Agent: Bad Bug",
                    'observatory': 'doma',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 18:30:00',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "",
                    'observatory': 'domb',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 19:24:59',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "Sequencer: Unavailable. Enclosure: Interlocked (Power)",
                    'observatory': 'domb',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 20:24:59',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "",
                    'observatory': 'domb',
                }
            },
            {
                '_source': {
                    'timestamp': '2016-10-01 20:44:58',
                    'site': 'tst',
                    'telescope': '1m0a',
                    'value_string': "Site Agent: Bad Bug",
                    'observatory': 'domb',
                }
            },
        ]

        self.tk1 = TelescopeKey('tst', 'doma', '1m0a')
        self.tk2 = TelescopeKey('tst', 'domb', '1m0a')

        self.es_patcher = patch('observation_portal.common.telescope_states.TelescopeStates._get_es_data')
        self.mock_es = self.es_patcher.start()
        self.mock_es.return_value = self.es_output

    def tearDown(self):
        super().tearDown()
        self.es_patcher.stop()


class TestTelescopeStates(TelescopeStatesFakeInput):
    def test_aggregate_states_1(self):
        start = datetime(2016, 10, 1)
        end = datetime(2016, 10, 2)
        telescope_states = TelescopeStates(start, end).get()

        self.assertIn(self.tk1, telescope_states)
        self.assertIn(self.tk2, telescope_states)

        doma_expected_available_state = {'telescope': 'tst.doma.1m0a',
                                         'event_type': 'AVAILABLE',
                                         'event_reason': 'Available for scheduling',
                                         'start': datetime(2016, 10, 1, 18, 24, 58, tzinfo=timezone.utc),
                                         'end': datetime(2016, 10, 1, 20, 44, 58, tzinfo=timezone.utc)
                                         }

        self.assertIn(doma_expected_available_state, telescope_states[self.tk1])

        domb_expected_available_state1 = {'telescope': 'tst.domb.1m0a',
                                          'event_type': 'AVAILABLE',
                                          'event_reason': 'Available for scheduling',
                                          'start': datetime(2016, 10, 1, 18, 30, 0, tzinfo=timezone.utc),
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

    @patch('observation_portal.common.telescope_states.get_site_rise_set_intervals')
    def test_telescope_availability_limits_interval(self, mock_intervals):
        mock_intervals.return_value = [(datetime(2016, 9, 30, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 9, 30, 21, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 1, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 1, 21, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 2, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 2, 21, 0, 0, tzinfo=timezone.utc))]
        start = datetime(2016, 9, 30, tzinfo=timezone.utc)
        end = datetime(2016, 10, 2, tzinfo=timezone.utc)
        telescope_availability = get_telescope_availability_per_day(start, end)

        self.assertIn(self.tk1, telescope_availability)
        self.assertIn(self.tk2, telescope_availability)

        doma_available_time = (datetime(2016, 10, 1, 20, 44, 58) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        doma_total_time = (datetime(2016, 10, 1, 21, 0, 0) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()

        doma_expected_availability = doma_available_time / doma_total_time
        self.assertAlmostEqual(doma_expected_availability, telescope_availability[self.tk1][0][1])

        domb_available_time = (datetime(2016, 10, 1, 19, 24, 59) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        domb_available_time += (datetime(2016, 10, 1, 20, 44, 58) - datetime(2016, 10, 1, 20, 24, 59)).total_seconds()
        domb_total_time = (datetime(2016, 10, 1, 21, 0, 0) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()

        domb_expected_availability = domb_available_time / domb_total_time
        self.assertAlmostEqual(domb_expected_availability, telescope_availability[self.tk2][0][1])

    @patch('observation_portal.common.telescope_states.get_site_rise_set_intervals')
    def test_telescope_availability_spans_interval(self, mock_intervals):
        mock_intervals.return_value = [(datetime(2016, 9, 30, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 9, 30, 21, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 1, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 1, 19, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 1, 19, 10, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 1, 19, 20, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 2, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 2, 21, 0, 0, tzinfo=timezone.utc))]
        start = datetime(2016, 9, 30, tzinfo=timezone.utc)
        end = datetime(2016, 10, 2, tzinfo=timezone.utc)
        telescope_availability = get_telescope_availability_per_day(start, end)

        self.assertIn(self.tk1, telescope_availability)
        self.assertIn(self.tk2, telescope_availability)

        doma_available_time = (datetime(2016, 10, 1, 19, 0, 0) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        doma_available_time += (datetime(2016, 10, 1, 19, 20, 0) - datetime(2016, 10, 1, 19, 10, 0)).total_seconds()
        doma_total_time = doma_available_time

        doma_expected_availability = doma_available_time / doma_total_time
        self.assertAlmostEqual(doma_expected_availability, telescope_availability[self.tk1][0][1])

        domb_expected_availability = 1.0
        self.assertAlmostEqual(domb_expected_availability, telescope_availability[self.tk2][0][1])

    @patch('observation_portal.common.telescope_states.get_site_rise_set_intervals')
    def test_telescope_availability_combine(self, mock_intervals):
        mock_intervals.return_value = [(datetime(2016, 9, 30, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 9, 30, 21, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 1, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 1, 21, 0, 0, tzinfo=timezone.utc)),
                                       (datetime(2016, 10, 2, 18, 30, 0, tzinfo=timezone.utc),
                                        datetime(2016, 10, 2, 21, 0, 0, tzinfo=timezone.utc))]
        start = datetime(2016, 9, 30, tzinfo=timezone.utc)
        end = datetime(2016, 10, 2, tzinfo=timezone.utc)
        telescope_availability = get_telescope_availability_per_day(start, end)

        self.assertIn(self.tk1, telescope_availability)
        self.assertIn(self.tk2, telescope_availability)

        combined_telescope_availability = combine_telescope_availabilities_by_site_and_class(telescope_availability)
        combined_key = TelescopeKey(self.tk1.site, '', self.tk1.telescope[:-1])

        self.assertIn(combined_key, combined_telescope_availability)

        doma_available_time = (datetime(2016, 10, 1, 20, 44, 58) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        doma_total_time = (datetime(2016, 10, 1, 21, 0, 0) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        doma_expected_availability = doma_available_time / doma_total_time

        domb_available_time = (datetime(2016, 10, 1, 19, 24, 59) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        domb_available_time += (datetime(2016, 10, 1, 20, 44, 58) - datetime(2016, 10, 1, 20, 24, 59)).total_seconds()
        domb_total_time = (datetime(2016, 10, 1, 21, 0, 0) - datetime(2016, 10, 1, 18, 30, 0)).total_seconds()
        domb_expected_availability = domb_available_time / domb_total_time

        total_expected_availability = (doma_expected_availability + domb_expected_availability) / 2.0
        self.assertAlmostEqual(total_expected_availability, combined_telescope_availability[combined_key][0][1])


class TelescopeStatesFromFile(TestCase):
    def setUp(self):
        self.configdb_null_patcher = patch('observation_portal.common.configdb.ConfigDB._get_configdb_data')
        mock_configdb_null = self.configdb_null_patcher.start()
        mock_configdb_null.return_value = {}
        self.configdb_patcher = patch('observation_portal.common.configdb.ConfigDB.get_instrument_types_per_telescope')
        self.mock_configdb = self.configdb_patcher.start()
        self.mock_configdb.return_value = {
            TelescopeKey(site='coj', enclosure='clma', telescope='2m0a'): ['2M0-FLOYDS-SCICAM',
                                                                             '2M0-SCICAM-SPECTRAL'],
            TelescopeKey(site='coj', enclosure='doma', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='coj', enclosure='domb', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='cpt', enclosure='domb', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='cpt', enclosure='domc', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='elp', enclosure='doma', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='lsc', enclosure='domb', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='lsc', enclosure='domc', telescope='1m0a'): ['1M0-SCICAM-SINISTRO'],
            TelescopeKey(site='ogg', enclosure='clma', telescope='0m4b'): ['0M4-SCICAM-SBIG'],
            TelescopeKey(site='ogg', enclosure='clma', telescope='2m0a'): ['2M0-FLOYDS-SCICAM'],
            TelescopeKey(site='sqa', enclosure='doma', telescope='0m8a'): ['0M8-SCICAM-SBIG',
                                                                             '0M8-NRES-SCICAM']}

        with open('observation_portal/common/test_data/es_telescope_states_data.txt', 'r') as input_file:
            self.es_output = json.loads(input_file.read())

        self.start = datetime(2016, 10, 1, tzinfo=timezone.utc)
        self.end = datetime(2016, 10, 10, tzinfo=timezone.utc)
        self.short_end = datetime(2016, 10, 4, tzinfo=timezone.utc)

        self.es_patcher = patch('observation_portal.common.telescope_states.TelescopeStates._get_es_data')
        self.mock_es = self.es_patcher.start()
        self.mock_es.return_value = self.es_output

    def tearDown(self):
        self.configdb_patcher.stop()
        self.configdb_null_patcher.stop()
        self.es_patcher.stop()


class TestTelescopeStatesFromFile(TelescopeStatesFromFile):
    def test_one_telescope_correctness(self):
        telescope_states = TelescopeStates(self.start, self.end).get()
        tak = TelescopeKey(site='lsc', enclosure='domb', telescope='1m0a')
        expected_events = [{'end': datetime(2016, 10, 3, 10, 25, 5, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 1, 0, 0, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 3, 10, 31, 20, tzinfo=timezone.utc),
                            'event_reason': 'Sequencer: Sequencer unavailable for scheduling',
                            'event_type': 'SEQUENCER_DISABLED',
                            'start': datetime(2016, 10, 3, 10, 25, 5, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 3, 16, 47, 42, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 3, 10, 31, 20, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 3, 17, 7, 49, tzinfo=timezone.utc),
                            'event_reason': 'Site Agent: No update since 2016-10-03T16:37:35',
                            'event_type': 'SITE_AGENT_UNRESPONSIVE',
                            'start': datetime(2016, 10, 3, 16, 47, 42, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 3, 23, 35, 58, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 3, 17, 7, 49, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 4, 1, 3, tzinfo=timezone.utc),
                            'event_reason': 'Weather: Sky transparency too low',
                            'event_type': 'NOT_OK_TO_OPEN',
                            'start': datetime(2016, 10, 3, 23, 35, 58, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 4, 1, 20, 46, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 4, 1, 3, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 4, 10, 30, 55, tzinfo=timezone.utc),
                            'event_reason': 'Weather: Sky transparency too low',
                            'event_type': 'NOT_OK_TO_OPEN',
                            'start': datetime(2016, 10, 4, 1, 20, 46, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 4, 21, 47, 6, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 4, 10, 30, 55, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 5, 0, 58, 26, tzinfo=timezone.utc),
                            'event_reason': 'Sequencer: Sequencer in MANUAL state',
                            'event_type': 'SEQUENCER_DISABLED',
                            'start': datetime(2016, 10, 4, 21, 47, 6, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 6, 16, 48, 6, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 5, 0, 58, 26, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 6, 16, 57, 19, tzinfo=timezone.utc),
                            'event_reason': 'Site Agent: No update since 2016-10-06T16:12:10',
                            'event_type': 'SITE_AGENT_UNRESPONSIVE',
                            'start': datetime(2016, 10, 6, 16, 48, 6, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 7, 10, 20, 44, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 6, 16, 57, 19, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 7, 10, 28, 58, tzinfo=timezone.utc),
                            'event_reason': 'Sequencer: Sequencer unavailable for scheduling',
                            'event_type': 'SEQUENCER_DISABLED',
                            'start': datetime(2016, 10, 7, 10, 20, 44, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 8, 10, 20, 25, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 7, 10, 28, 58, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 8, 10, 28, 36, tzinfo=timezone.utc),
                            'event_reason': 'Sequencer: Sequencer unavailable for scheduling',
                            'event_type': 'SEQUENCER_DISABLED',
                            'start': datetime(2016, 10, 8, 10, 20, 25, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'},
                           {'end': datetime(2016, 10, 10, 0, 0, tzinfo=timezone.utc),
                            'event_reason': 'Available for scheduling',
                            'event_type': 'AVAILABLE',
                            'start': datetime(2016, 10, 8, 10, 28, 36, tzinfo=timezone.utc),
                            'telescope': 'lsc.domb.1m0a'}]
        # looked in depth at lsc.domb.1m0a in the date range to verify correctness of this
        # data is available on the telescope_events index of elasticsearch
        self.assertEqual(telescope_states[tak], expected_events)

    def test_states_no_enclosure_interlock(self):
        telescope_states = TelescopeStates(self.start, self.end).get()

        self.assertNotIn("ENCLOSURE_INTERLOCK", telescope_states)

    def test_states_end_time_after_start(self):
        telescope_states = TelescopeStates(self.start, self.end).get()

        for _, events in telescope_states.items():
            for event in events:
                self.assertTrue(event['start'] <= event['end'])

    def test_states_no_duplicate_consecutive_states(self):
        telescope_states = TelescopeStates(self.start, self.end).get()

        for _, events in telescope_states.items():
            previous_event = None
            for event in events:
                if previous_event:
                    self.assertTrue(previous_event['event_type'] != event['event_type'] or
                                    previous_event['event_reason'] != event['event_reason'])

                previous_event = event


class TestRiseSetUtils(TestCase):
    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_site_rise_set_intervals_should_return_an_interval(self):
        start = timezone.datetime(year=2017, month=5, day=5, tzinfo=timezone.utc)
        end = timezone.datetime(year=2017, month=5, day=6, tzinfo=timezone.utc)
        self.assertTrue(rise_set_utils.get_site_rise_set_intervals(start=start, end=end, site_code='tst'))

    def test_get_largest_rise_set_interval_only_uses_one_site(self):
        configdb_patcher = patch(
            'observation_portal.common.configdb.ConfigDB.get_sites_with_instrument_type_and_location'
        )
        mock_configdb = configdb_patcher.start()
        mock_configdb.return_value = {
            'tst': {
                'latitude': -30.1673833333,
                'longitude': -70.8047888889,
                'horizon': 15.0,
                'altitude': 100.0,
                'ha_limit_pos': 4.6,
                'ha_limit_neg': -4.6,
                'zenith_blind_spot': 0.0
            },
            'abc': {
                'latitude': -32.3805542,
                'longitude': 20.8101815,
                'horizon': 15.0,
                'altitude': 100.0,
                'ha_limit_pos': 4.6,
                'ha_limit_neg': -4.6,
                'zenith_blind_spot': 0.0
            }
        }
        configdb_patcher2 = patch(
            'observation_portal.common.configdb.ConfigDB.get_telescopes_with_instrument_type_and_location')
        mock_configdb2 = configdb_patcher2.start()
        mock_configdb2.return_value = {
            '1m0a.doma.tst': {
                'latitude': -30.1673833333,
                'longitude':-70.8047888889,
                'horizon': 15.0,
                'altitude': 100.0,
                'ha_limit_pos': 4.6,
                'ha_limit_neg': -4.6,
                'zenith_blind_spot': 0.0
            },
            '1m0a.doma.abc': {
                'latitude': -32.3805542,
                'longitude': 20.8101815,
                 'horizon': 15.0,
                 'altitude': 100.0,
                 'ha_limit_pos': 4.6,
                 'ha_limit_neg': -4.6,
                 'zenith_blind_spot': 0.0
            }
        }

        request_dict = {'location': {'telescope_class': '1m0'},
                        'windows': [
                            {
                                'start': datetime(2016, 9, 4),
                                'end': datetime(2016, 9, 5)
                            }
                        ],
                        'configurations': [
                            {
                                'instrument_type': '1M0-SCICAM-SINISTRO',
                                'instrument_configs': [
                                    {
                                        'exposure_time': 6000,
                                        'exposure_count': 5
                                    }
                                ],
                                'target': {
                                    'type': 'ICRS',
                                    'ra': 35.0,
                                    'dec': -53.0,
                                    'proper_motion_ra': 0.0,
                                    'proper_motion_dec': 0.0,
                                    'epoch': 2000,
                                    'parallax': 0.0
                                },
                                'constraints': {
                                    'max_airmass': 2.0,
                                    'min_lunar_distance': 30.0
                                }
                            }
                        ]}
        filtered_intervals = rise_set_utils.get_filtered_rise_set_intervals_by_site(request_dict)
        largest_interval = rise_set_utils.get_largest_interval(filtered_intervals)
        duration = timedelta(seconds=30000)
        self.assertGreater(duration, largest_interval)  # The duration is greater than the largest interval at a site

        combined_intervals = Intervals().union(
            [Intervals(timepoints=fi) for fi in filtered_intervals.values()]).toTupleList()
        largest_combined_interval = rise_set_utils.get_largest_interval({'tst': combined_intervals})
        self.assertLess(duration, largest_combined_interval)  # The duration is less then combined largest intervals

        configdb_patcher.stop()
        configdb_patcher2.stop()

    def test_get_site_rise_set_intervals_should_not_return_an_interval(self):
        start = timezone.datetime(year=2017, month=5, day=5, tzinfo=timezone.utc)
        end = timezone.datetime(year=2017, month=5, day=6, tzinfo=timezone.utc)
        self.assertFalse(rise_set_utils.get_site_rise_set_intervals(start=start, end=end, site_code='bpl'))
