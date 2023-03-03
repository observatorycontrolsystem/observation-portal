from django.utils import timezone
from django.test import TestCase
from mixer.backend.django import mixer
from rest_framework.serializers import ValidationError
from datetime import datetime, timedelta
from unittest.mock import patch
import math
import copy

from observation_portal.requestgroups.models import (
    Request, Configuration, Target, RequestGroup, Window, Location, Constraints, InstrumentConfig,
    AcquisitionConfig, GuidingConfig
)
from observation_portal.proposals.models import Proposal, TimeAllocation, Semester
from observation_portal.common.configdb import ConfigDBException, configdb
from observation_portal.common.test_helpers import SetTimeMixin
from observation_portal.requestgroups.duration_utils import PER_CONFIGURATION_STARTUP_TIME
from observation_portal.requestgroups.serializers import ConfigurationTypeValidationHelper, InstrumentTypeValidationHelper, ModeValidationHelper
from observation_portal.requestgroups.test.test_api import generic_payload
from observation_portal.observations.models import Observation


class TestRequestGroupTotalDuration(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            instrument_types=['1M0-SCICAM-SBIG'], rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.rg_single = mixer.blend(RequestGroup, proposal=self.proposal, operator='SINGLE',
                                     observation_type=RequestGroup.NORMAL)
        self.rg_many = mixer.blend(RequestGroup, proposal=self.proposal,
                                   observation_type=RequestGroup.NORMAL)

        self.request = mixer.blend(Request, request_group=self.rg_single)
        self.requests = mixer.cycle(3).blend(Request, request_group=self.rg_many)

        self.configuration_expose = mixer.blend(
            Configuration, request=self.request, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.configuration_exposes = mixer.cycle(3).blend(
            Configuration, request=(r for r in self.requests),  instrument_type='1M0-SCICAM-SBIG', type='EXPOSE'
        )
        self.instrument_config = mixer.blend(
            InstrumentConfig, configuration=self.configuration_expose, mode='1m0_sbig_2',
            optical_elements={'filter': 'blah'}, exposure_time=600, exposure_count=2, extra_params={'bin_x': 2, 'bin_y': 2}
        )
        self.instrument_configs = mixer.cycle(3).blend(
            InstrumentConfig, configuration=(c for c in self.configuration_exposes), extra_params={'bin_x': 2, 'bin_y': 2},
            optical_elements=({'filter': f} for f in ('uv', 'uv', 'ir')), mode='1m0_sbig_2', exposure_time=1000, exposure_count=1,
        )
        mixer.blend(
            Window, request=self.request, start=datetime(2016, 9, 29, tzinfo=timezone.utc),
            end=datetime(2016, 10, 29, tzinfo=timezone.utc)
        )
        mixer.cycle(3).blend(
            Window, request=(r for r in self.requests), start=datetime(2016, 9, 29, tzinfo=timezone.utc),
            end=datetime(2016, 10, 29, tzinfo=timezone.utc)
        )
        mixer.blend(Target, configuration=self.configuration_expose)
        mixer.cycle(3).blend(Target, configuration=(c for c in self.configuration_exposes))

        mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.cycle(3).blend(Location, request=(r for r in self.requests), telescope_class='1m0')

        mixer.blend(Constraints, configuration=self.configuration_expose)
        mixer.cycle(3).blend(Constraints, configuration=(c for c in self.configuration_exposes))

        mixer.blend(AcquisitionConfig, configuration=self.configuration_expose)
        mixer.cycle(3).blend(AcquisitionConfig, configuration=(c for c in self.configuration_exposes))

        mixer.blend(GuidingConfig, configuration=self.configuration_expose)
        mixer.cycle(3).blend(GuidingConfig, configuration=(c for c in self.configuration_exposes))

    def test_single_rg_total_duration(self):
        request_duration = self.request.duration
        total_duration = self.rg_single.total_duration
        taks = self.request.time_allocation_keys
        self.assertEqual(request_duration, total_duration[taks[0]])

    def test_many_rg_takes_highest_duration(self):
        self.rg_many.operator = 'MANY'
        self.rg_many.save()

        highest_duration = max(r.duration for r in self.requests)
        total_duration = self.rg_many.total_duration
        taks = self.requests[0].time_allocation_keys
        self.assertEqual(highest_duration, total_duration[taks[0]])

    def test_and_rg_takes_sum_of_durations(self):
        self.rg_many.operator = 'AND'
        self.rg_many.save()

        sum_duration = sum(r.duration for r in self.requests)
        total_duration = self.rg_many.total_duration
        taks = self.requests[0].time_allocation_keys
        self.assertEqual(sum_duration, total_duration[taks[0]])


class TestRequestDuration(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.request = mixer.blend(Request)
        mixer.blend(Location, request=self.request)

        self.configuration_expose = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE')
        self.configuration_expose_2 = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE')
        self.configuration_expose_3 = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG', type='EXPOSE')
        self.configuration_spectrum = mixer.blend(Configuration, instrument_type='2M0-FLOYDS-SCICAM', type='SPECTRUM')
        self.configuration_spectrum_2 = mixer.blend(Configuration, instrument_type='2M0-FLOYDS-SCICAM', type='SPECTRUM')
        self.configuration_arc = mixer.blend(Configuration, instrument_type='2M0-FLOYDS-SCICAM', type='ARC')
        self.configuration_lampflat = mixer.blend(Configuration, instrument_type='2M0-FLOYDS-SCICAM', type='LAMP_FLAT')
        self.configuration_repeat_expose = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG',
                                                       type='REPEAT_EXPOSE', repeat_duration=500)

        configurations = [self.configuration_expose, self.configuration_spectrum, self.configuration_arc,
                          self.configuration_lampflat, self.configuration_expose_2, self.configuration_expose_3,
                          self.configuration_spectrum_2, self.configuration_repeat_expose]

        mixer.cycle(len(configurations)).blend(AcquisitionConfig, configuration=(c for c in configurations))
        mixer.cycle(len(configurations)).blend(GuidingConfig, configuration=(c for c in configurations))
        mixer.cycle(len(configurations)).blend(Constraints, configuration=(c for c in configurations))
        mixer.cycle(len(configurations)).blend(Target, configuration=(c for c in configurations), type='ICRS',
                                               ra=10.0, dec=10.0, proper_motion_ra=0, proper_motion_dec=0)

        self.instrument_config_expose = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=600, exposure_count=2,
            optical_elements={'filter': 'blah'}, mode='1m0_sbig_2'
        )
        self.instrument_config_expose_1 = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=1000, exposure_count=1,
            optical_elements={'filter': 'uv'}, mode='1m0_sbig_2'
        )
        self.instrument_config_expose_2 = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=10, exposure_count=5,
            optical_elements={'filter': 'uv'}, mode='1m0_sbig_2'
        )
        self.instrument_config_expose_3 = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=3, exposure_count=3,
            optical_elements={'filter': 'ir'}, mode='1m0_sbig_2'
        )
        self.instrument_config_spectrum = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 1, 'bin_y': 1}, exposure_time=1800, exposure_count=1,
            optical_elements={'slit': 'slit_1.6as'}, configuration=self.configuration_spectrum, mode='2m0_floyds_1'
        )
        self.instrument_config_arc = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 1, 'bin_y': 1}, exposure_time=30, exposure_count=2,
            optical_elements={'slit': 'slit_1.6as'}, configuration=self.configuration_arc, mode='2m0_floyds_1'
        )
        self.instrument_config_lampflat = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 1, 'bin_y': 1}, exposure_time=60, exposure_count=1,
            optical_elements={'slit': 'slit_1.6as'}, configuration=self.configuration_lampflat, mode='2m0_floyds_1'
        )
        self.instrument_config_repeat_expose = mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=30, exposure_count=1,
            optical_elements={'filter': 'b'}, mode='1m0_sbig_2', configuration=self.configuration_repeat_expose
        )

        self.instrument_change_overhead_1m = 0
        self.minimum_slew_time = 2

        self.sbig_fixed_overhead_per_exposure = 1
        self.sbig_filter_optical_element_change_overhead = 2
        self.sbig_front_padding = 90
        self.sbig_readout_time2 = 14.5

        self.floyds_fixed_overhead_per_exposure = 0.5
        self.floyds_filter_change_time = 0
        self.floyds_front_padding = 240
        self.floyds_readout_time1 = 25
        self.floyds_config_change_time = 30
        self.floyds_acquire_processing_time = 90
        self.floyds_acquire_exposure_time = 30

    def test_ccd_single_configuration_request_duration(self):
        self.configuration_expose.request = self.request
        self.configuration_expose.save()

        self.instrument_config_expose.configuration = self.configuration_expose
        self.instrument_config_expose.save()

        duration = self.request.duration
        exp_count = self.instrument_config_expose.exposure_count
        exp_time = self.instrument_config_expose.exposure_time

        self.assertEqual(duration, math.ceil(exp_count*(exp_time + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure) + self.sbig_front_padding + self.sbig_filter_optical_element_change_overhead + PER_CONFIGURATION_STARTUP_TIME + self.instrument_change_overhead_1m + self.minimum_slew_time))

    def test_ccd_single_configuration_duration(self):
        self.instrument_config_expose.configuration = self.configuration_expose
        self.instrument_config_expose.save()

        duration = self.configuration_expose.duration

        exp_time = self.instrument_config_expose.exposure_time
        exp_count = self.instrument_config_expose.exposure_count

        self.assertEqual(duration, (exp_count*(exp_time + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure) + PER_CONFIGURATION_STARTUP_TIME))

    def test_ccd_multiple_instrument_configuration_request_duration(self):
        self.configuration_expose.request = self.request
        self.configuration_expose.save()
        self.instrument_config_expose_1.configuration = self.configuration_expose
        self.instrument_config_expose_1.save()
        self.instrument_config_expose_2.configuration = self.configuration_expose
        self.instrument_config_expose_2.save()
        self.instrument_config_expose_3.configuration = self.configuration_expose
        self.instrument_config_expose_3.save()

        duration = self.request.duration

        exp_time1 = self.instrument_config_expose_1.exposure_time
        exp_count1 = self.instrument_config_expose_1.exposure_count
        exp_time2 = self.instrument_config_expose_2.exposure_time
        exp_count2 = self.instrument_config_expose_2.exposure_count
        exp_time3 = self.instrument_config_expose_3.exposure_time
        exp_count3 = self.instrument_config_expose_3.exposure_count

        exp_1_duration = exp_count1*(exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2*(exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3*(exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)

        num_filter_changes = 2

        self.assertEqual(duration, math.ceil(exp_1_duration + exp_2_duration + exp_3_duration + self.sbig_front_padding + num_filter_changes*self.sbig_filter_optical_element_change_overhead + (PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time)))

    def test_single_repeat_configuration_duration(self):
        self.configuration_repeat_expose.request = self.request
        self.configuration_repeat_expose.save()

        configuration_duration = self.configuration_repeat_expose.repeat_duration
        self.assertEqual(configuration_duration, self.configuration_repeat_expose.duration)

        mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=30, exposure_count=1,
            optical_elements={'filter': 'g'}, mode='1m0_sbig_2', configuration=self.configuration_repeat_expose
        )
        mixer.blend(
            InstrumentConfig, extra_params={'bin_x': 2, 'bin_y': 2}, exposure_time=30, exposure_count=1,
            optical_elements={'filter': 'r'}, mode='1m0_sbig_2'
        )
        # configuration duration is unchanged after adding instrument configs
        self.assertEqual(configuration_duration, self.configuration_repeat_expose.duration)

    def test_repeat_configuration_multi_config_request_duration(self):
        self.configuration_repeat_expose.request = self.request
        self.configuration_repeat_expose.save()
        self.configuration_expose.request = self.request
        self.configuration_expose.save()
        self.configuration_expose_2.request = self.request
        self.configuration_expose_2.save()
        self.instrument_config_expose_1.configuration = self.configuration_expose
        self.instrument_config_expose_1.save()
        self.instrument_config_expose_2.configuration = self.configuration_expose_2
        self.instrument_config_expose_2.save()

        exp_time1 = self.instrument_config_expose_1.exposure_time
        exp_count1 = self.instrument_config_expose_1.exposure_count
        exp_time2 = self.instrument_config_expose_2.exposure_time
        exp_count2 = self.instrument_config_expose_2.exposure_count
        exp_1_duration = exp_count1 * (exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2 * (exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        repeat_config_duration = self.configuration_repeat_expose.repeat_duration
        num_configurations = 3
        num_filter_changes = 2
        duration = self.request.duration

        self.assertEqual(duration, math.ceil(exp_1_duration + exp_2_duration + (repeat_config_duration - PER_CONFIGURATION_STARTUP_TIME) + self.sbig_front_padding + num_configurations*(
            PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time) + num_filter_changes*self.sbig_filter_optical_element_change_overhead))

    def test_ccd_multiple_configuration_request_duration(self):
        self.instrument_config_expose_1.configuration = self.configuration_expose
        self.instrument_config_expose_1.save()
        self.instrument_config_expose_2.configuration = self.configuration_expose_2
        self.instrument_config_expose_2.save()
        self.instrument_config_expose_3.configuration = self.configuration_expose_3
        self.instrument_config_expose_3.save()
        self.configuration_expose.request = self.request
        self.configuration_expose.save()
        self.configuration_expose_2.request = self.request
        self.configuration_expose_2.save()
        self.configuration_expose_3.request = self.request
        self.configuration_expose_3.save()
        duration = self.request.duration

        exp_time1 = self.instrument_config_expose_1.exposure_time
        exp_count1 = self.instrument_config_expose_1.exposure_count
        exp_time2 = self.instrument_config_expose_2.exposure_time
        exp_count2 = self.instrument_config_expose_2.exposure_count
        exp_time3 = self.instrument_config_expose_3.exposure_time
        exp_count3 = self.instrument_config_expose_3.exposure_count

        exp_1_duration = exp_count1 * (exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2 * (exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3 * (exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        num_configurations = 3
        num_filter_changes = 2

        self.assertEqual(duration, math.ceil(exp_1_duration + exp_2_duration + exp_3_duration + self.sbig_front_padding + num_configurations*(PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time) + num_filter_changes*self.sbig_filter_optical_element_change_overhead))

    def test_ccd_multiple_configuration_duration(self):
        self.instrument_config_expose_1.configuration = self.configuration_expose
        self.instrument_config_expose_1.save()
        self.instrument_config_expose_2.configuration = self.configuration_expose_2
        self.instrument_config_expose_2.save()
        self.instrument_config_expose_3.configuration = self.configuration_expose_3
        self.instrument_config_expose_3.save()
        duration = self.configuration_expose.duration
        duration += self.configuration_expose_2.duration
        duration += self.configuration_expose_3.duration

        exp_time1 = self.instrument_config_expose_1.exposure_time
        exp_count1 = self.instrument_config_expose_1.exposure_count
        exp_time2 = self.instrument_config_expose_2.exposure_time
        exp_count2 = self.instrument_config_expose_2.exposure_count
        exp_time3 = self.instrument_config_expose_3.exposure_time
        exp_count3 = self.instrument_config_expose_3.exposure_count

        exp_1_duration = exp_count1 * (exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2 * (exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3 * (exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        num_configurations = 3

        self.assertEqual(duration, (exp_1_duration + exp_2_duration + exp_3_duration + num_configurations*(PER_CONFIGURATION_STARTUP_TIME)))

    def test_floyds_single_configuration_request_duration_with_acquire_on(self):
        self.configuration_spectrum.request = self.request
        self.configuration_spectrum.acquisition_config.mode = 'WCS'
        self.configuration_spectrum.acquisition_config.save()
        self.configuration_spectrum.save()

        duration = self.request.duration

        exp_time = 1800
        exp_count = 1

        self.assertEqual(duration, math.ceil(exp_count*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + self.floyds_front_padding + self.floyds_acquire_processing_time + self.floyds_acquire_exposure_time + PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time))

    def test_floyds_uses_supplied_acquisition_config_exposure_time(self):
        self.configuration_spectrum.request = self.request
        self.configuration_spectrum.acquisition_config.mode = 'WCS'
        self.configuration_spectrum.acquisition_config.save()
        self.configuration_spectrum.save()

        duration = self.request.duration

        self.configuration_spectrum.acquisition_config.exposure_time = 20.0  # Default for test floyds is 30sec
        self.configuration_spectrum.acquisition_config.save()
        self.configuration_spectrum.save()

        del self.request.duration
        new_duration = self.request.duration

        self.assertEqual(new_duration, duration - 10)

    def test_floyds_multiple_spectrum_configuration_request_duration_with_acquire_on(self):
        self.configuration_spectrum.request = self.request
        self.configuration_spectrum.acquisition_config.mode = 'WCS'
        self.configuration_spectrum.acquisition_config.save()
        self.configuration_spectrum.save()

        mixer.blend(
            InstrumentConfig, configuration=self.configuration_spectrum_2, extra_params={'bin_x': 1, 'bin_y': 1},
            exposure_time=1800, exposure_count=1, mode='2m0_floyds_1'
        )
        self.configuration_spectrum_2.request = self.request
        self.configuration_spectrum_2.acquisition_config.mode = 'WCS'
        self.configuration_spectrum_2.acquisition_config.save()
        self.configuration_spectrum_2.save()

        duration = self.request.duration

        exp_time = 1800
        exp_count = 1
        num_spectrum_configurations = 2

        self.assertEqual(duration, math.ceil(exp_count*num_spectrum_configurations*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + self.floyds_front_padding + num_spectrum_configurations*(self.floyds_acquire_processing_time + PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time + self.floyds_acquire_exposure_time)))

    def test_floyds_single_configuration_duration(self):
        duration = self.configuration_spectrum.duration

        exp_time = self.instrument_config_spectrum.exposure_time
        exp_count = self.instrument_config_spectrum.exposure_count

        self.assertEqual(duration, (exp_count*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + PER_CONFIGURATION_STARTUP_TIME))

    def test_floyds_multiple_configuration_request_duration_with_acquire_on(self):
        self.configuration_lampflat.request = self.request
        self.configuration_lampflat.save()
        self.configuration_arc.request = self.request
        self.configuration_arc.save()
        self.configuration_spectrum.request = self.request
        self.configuration_spectrum.acquisition_config.mode = 'WCS'
        self.configuration_spectrum.acquisition_config.save()
        self.configuration_spectrum.save()

        duration = self.request.duration

        exp_time_s = self.instrument_config_spectrum.exposure_time
        exp_count_s = self.instrument_config_spectrum.exposure_count
        exp_time_a = self.instrument_config_arc.exposure_time
        exp_count_a = self.instrument_config_arc.exposure_count
        exp_time_l = self.instrument_config_lampflat.exposure_time
        exp_count_l = self.instrument_config_lampflat.exposure_count

        exp_s_duration = exp_count_s*(exp_time_s + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_a_duration = exp_count_a*(exp_time_a + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_l_duration = exp_count_l*(exp_time_l + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)

        num_configurations = 3

        self.assertEqual(duration, math.ceil(exp_s_duration + exp_a_duration + exp_l_duration + self.floyds_front_padding + self.floyds_acquire_processing_time + self.floyds_acquire_exposure_time + (num_configurations-1)*self.floyds_config_change_time + num_configurations*(PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time)))

    def test_floyds_multiple_configuration_duration(self):
        duration = self.configuration_lampflat.duration
        duration += self.configuration_arc.duration
        duration += self.configuration_spectrum.duration

        exp_time_s = self.instrument_config_spectrum.exposure_time
        exp_count_s = self.instrument_config_spectrum.exposure_count
        exp_time_a = self.instrument_config_arc.exposure_time
        exp_count_a = self.instrument_config_arc.exposure_count
        exp_time_l = self.instrument_config_lampflat.exposure_time
        exp_count_l = self.instrument_config_lampflat.exposure_count

        exp_s_duration = exp_count_s*(exp_time_s + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_a_duration = exp_count_a*(exp_time_a + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_l_duration = exp_count_l*(exp_time_l + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)

        num_configurations = 3

        self.assertEqual(duration, (exp_s_duration + exp_a_duration + exp_l_duration + num_configurations*(PER_CONFIGURATION_STARTUP_TIME)))

    def test_configuration_repeats_single_configuration_request_duration(self):
        self.configuration_expose.request = self.request
        self.configuration_expose.save()
        self.request.configuration_repeats = 3
        self.request.save()

        self.instrument_config_expose.configuration = self.configuration_expose
        self.instrument_config_expose.save()

        duration = self.request.duration
        exp_count = self.instrument_config_expose.exposure_count
        exp_time = self.instrument_config_expose.exposure_time

        configuration_duration = exp_count*(exp_time + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure) + self.sbig_filter_optical_element_change_overhead + PER_CONFIGURATION_STARTUP_TIME + self.instrument_change_overhead_1m + self.minimum_slew_time
        self.assertEqual(duration, math.ceil( self.request.configuration_repeats * configuration_duration + self.sbig_front_padding))

    def test_configuration_repeats_multi_configuration_request_duration(self):
        self.configuration_expose.request = self.request
        self.configuration_expose.save()
        self.instrument_config_expose_1.configuration = self.configuration_expose
        self.instrument_config_expose_1.save()
        self.instrument_config_expose_2.configuration = self.configuration_expose
        self.instrument_config_expose_2.save()
        self.instrument_config_expose_3.configuration = self.configuration_expose
        self.instrument_config_expose_3.save()

        self.request.configuration_repeats = 3
        self.request.save()

        duration = self.request.duration

        exp_time1 = self.instrument_config_expose_1.exposure_time
        exp_count1 = self.instrument_config_expose_1.exposure_count
        exp_time2 = self.instrument_config_expose_2.exposure_time
        exp_count2 = self.instrument_config_expose_2.exposure_count
        exp_time3 = self.instrument_config_expose_3.exposure_time
        exp_count3 = self.instrument_config_expose_3.exposure_count

        exp_1_duration = exp_count1*(exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2*(exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3*(exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)

        num_filter_changes = 2
        configuration_duration = exp_1_duration + exp_2_duration + exp_3_duration + num_filter_changes*self.sbig_filter_optical_element_change_overhead + (PER_CONFIGURATION_STARTUP_TIME + self.minimum_slew_time)

        self.assertEqual(duration, math.ceil(self.request.configuration_repeats * configuration_duration + self.sbig_front_padding))

    def test_configuration_repeats_repeat_configuration_request_duration(self):
        self.configuration_repeat_expose.request = self.request
        self.configuration_repeat_expose.save()
        self.request.configuration_repeats = 2
        self.request.save()

        configuration_duration = self.configuration_repeat_expose.repeat_duration
        self.assertEqual(configuration_duration, self.configuration_repeat_expose.duration)

        # Add the non-repeat parts back to the configuration duration
        configuration_duration += + self.sbig_filter_optical_element_change_overhead + self.instrument_change_overhead_1m + self.minimum_slew_time

        duration = self.request.duration
        self.assertEqual(duration, math.ceil( self.request.configuration_repeats * configuration_duration + self.sbig_front_padding))

    def test_get_duration_from_non_existent_camera(self):
        self.configuration_expose.instrument_type = 'FAKE-CAMERA'
        self.configuration_expose.save()
        self.instrument_config_expose.configuration = self.configuration_expose
        self.instrument_config_expose.save()

        with self.assertRaises(ConfigDBException) as context:
            _ = self.configuration_expose.duration
            self.assertTrue('not found in configdb' in context.exception)


class TestValidationHelper(TestCase):
    def setUp(self) -> None:
        self.mock_instrument_type = {'code': '1M0-SCICAM-SBIG',
                                     'validation_schema': {'extra_params': {'type': 'dict',
                                                                            'schema': {'defocus': {'type': 'float',
                                                                                                   'min': -5.0,
                                                                                                   'max': 5.0}}},
                                                           'exposure_time': {'type': 'integer', 'min': 0}}}

        self.mock_configuration_type_properties = {'SKY_FLAT': {
            "validation_schema": {
                "exposure_time": {
                    "type": "float",
                    "default": 2.0
                }
            }
        }}
        self.generic_payload = copy.deepcopy(generic_payload)
        self.request_instrument_type = self.generic_payload['requests'][0]['configurations'][0]['instrument_type']
        self.instrument_config = self.generic_payload['requests'][0]['configurations'][0]['instrument_configs'][0]
        self.muscat_extra_params = {'exposure_time_g': 60,
                                    'exposure_time_r': 90,
                                    'exposure_time_i': 60,
                                    'exposure_time_z': 120,
                                    'exposure_mode': 'SYNCHRONOUS'}

    @patch('observation_portal.requestgroups.serializers.configdb.get_instrument_type_by_code')
    def test_validate_instrument_config_and_extra_params_good_config(self, mock_instrument_type):
        instrument_config = self.instrument_config.copy()
        mock_instrument_type.return_value = self.mock_instrument_type
        instrument_config['extra_params'] = {'defocus': 2.0}

        validation_helper = InstrumentTypeValidationHelper(self.request_instrument_type)
        validated_config = validation_helper.validate(instrument_config)

        self.assertEqual(instrument_config, validated_config)

    @patch('observation_portal.requestgroups.serializers.configdb.get_instrument_type_by_code')
    def test_validate_instrument_config_and_extra_params_bad_config(self, mock_instrument_type):
        instrument_config = self.instrument_config.copy()
        mock_instrument_type.return_value = self.mock_instrument_type
        instrument_config['extra_params'] = {'defocus': 2.0}
        instrument_config['exposure_time'] = -20

        validation_helper = InstrumentTypeValidationHelper(self.request_instrument_type)
        with self.assertRaises(ValidationError) as e:
            validation_helper.validate(instrument_config)
        self.assertIn('exposure_time', str(e.exception))

    def test_validate_mode_config_filled_in_when_missing(self):
        guiding_config = {}
        modes = configdb.get_modes_by_type(self.request_instrument_type)
        validation_helper = ModeValidationHelper('guiding', self.request_instrument_type, modes['guiding'])

        validated_config = validation_helper.validate(guiding_config)
        self.assertEqual(validated_config['mode'], 'OFF')

    def test_validate_mode_config_good_config(self):
        instrument_config = self.instrument_config.copy()
        instrument_config['mode'] = "1m0_sbig_1"
        instrument_config['extra_params'] = {'bin_x': 1, 'bin_y': 1}
        modes = configdb.get_modes_by_type(self.request_instrument_type)

        validation_helper = ModeValidationHelper('readout', self.request_instrument_type, modes['readout'])
        validated_config = validation_helper.validate(instrument_config)

        self.assertEqual(validated_config, instrument_config)

    def test_validate_mode_config_bad_config(self):
        instrument_config = self.instrument_config.copy()
        instrument_config['mode'] = "1m0_sbig_2"
        instrument_config['extra_params'] = {'bin_x': 1, 'bin_y': 2}
        modes = configdb.get_modes_by_type(self.request_instrument_type)

        validation_helper = ModeValidationHelper('readout', self.request_instrument_type, modes['readout'])
        with self.assertRaises(ValidationError) as e:
            validation_helper.validate(instrument_config)
        self.assertIn('bin_x', str(e.exception))

    def test_validate_extra_param_mode_good_config(self):
        instrument_config = self.instrument_config.copy()
        instrument_type = "2M0-SCICAM-MUSCAT"
        instrument_config['instrument_type'] = instrument_type
        instrument_config['extra_params'] = self.muscat_extra_params
        modes = configdb.get_modes_by_type(instrument_type)

        validation_helper = ModeValidationHelper('exposure', instrument_type, modes['exposure'],
                                                 is_extra_param_mode=True)
        validated_instrument_config = validation_helper.validate(instrument_config)

        self.assertEqual(instrument_config, validated_instrument_config)

    def test_validate_extra_param_mode_bad_config(self):
        instrument_config = self.instrument_config.copy()
        instrument_type = "2M0-SCICAM-MUSCAT"
        instrument_config['instrument_type'] = instrument_type
        instrument_config['extra_params'] = self.muscat_extra_params.copy()
        del instrument_config['extra_params']['exposure_mode']
        modes = configdb.get_modes_by_type(instrument_type)

        validation_helper = ModeValidationHelper('exposure', instrument_type, modes['exposure'],
                                                 is_extra_param_mode=True)

        with self.assertRaises(ValidationError) as e:
            validation_helper.validate(instrument_config)
        self.assertIn('exposure_mode', str(e.exception))

    @patch('observation_portal.requestgroups.serializers.configdb.get_configuration_types')
    def test_validate_exposure_time_no_exposure_time_set(self, mock_configuration_type_properties):
        instrument_config = self.instrument_config.copy()
        mock_configuration_type_properties.return_value = self.mock_configuration_type_properties
        del instrument_config['exposure_time']

        validation_helper = ConfigurationTypeValidationHelper('FAKE-CAMERA', 'SKY_FLAT')
        validated_instrument_config = validation_helper.validate(instrument_config)

        self.assertEqual(validated_instrument_config['exposure_time'], 2.0)


class TestRequestSemester(SetTimeMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.semester_1 = mixer.blend(Semester, start=datetime(2016, 1, 1, 0, 0, 0, tzinfo=timezone.utc), end=datetime(2016, 1, 31, 23, 59, 59, tzinfo=timezone.utc))
        self.semester_2 = mixer.blend(Semester, start=datetime(2016, 2, 1, 0, 0, 0, tzinfo=timezone.utc), end=datetime(2016, 2, 29, 23, 59, 59, tzinfo=timezone.utc))
        self.request = mixer.blend(Request)

    def test_get_semester(self):
        mixer.blend(Window, request=self.request, start=self.semester_1.start + timedelta(days=1), end=self.semester_1.end - timedelta(days=1))
        mixer.blend(Window, request=self.request, start=self.semester_1.start + timedelta(days=2), end=self.semester_1.end - timedelta(days=2))
        semester = self.request.semester
        self.assertEqual(semester.id, self.semester_1.id)

    def test_get_semester_for_request_without_observations_when_windows_span_multiple_semesters(self):
        mixer.blend(Window, request=self.request, start=self.semester_1.start + timedelta(days=1), end=self.semester_1.end - timedelta(days=1))
        mixer.blend(Window, request=self.request, start=self.semester_2.start - timedelta(days=1), end=self.semester_2.start + timedelta(days=1))
        semester = self.request.semester
        # Should fall into the semester with the earliest window start time
        self.assertEqual(semester.id, self.semester_1.id)

    def test_get_semester_for_request_with_observations_when_windows_span_multiple_semesters(self):
        mixer.blend(Window, request=self.request, start=self.semester_1.start + timedelta(days=1), end=self.semester_1.end - timedelta(days=1))
        mixer.blend(Window, request=self.request, start=self.semester_2.start - timedelta(days=1), end=self.semester_2.start + timedelta(days=1))
        mixer.blend(Observation, request=self.request, start=self.semester_2.start + timedelta(hours=1), end=self.semester_2.start + timedelta(hours=2))
        semester = self.request.semester
        # Should fall into the semester that contains any observation
        self.assertEqual(semester.id, self.semester_2.id)
