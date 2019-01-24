from django.utils import timezone
from django.test import TestCase
from mixer.backend.django import mixer
from datetime import datetime
import math

from valhalla.userrequests.models import Request, Molecule, Target, UserRequest, Window, Location, Constraints
from valhalla.proposals.models import Proposal, TimeAllocation, Semester
from valhalla.common.configdb import ConfigDBException
from valhalla.common.test_helpers import ConfigDBTestMixin, SetTimeMixin
from valhalla.userrequests.duration_utils import PER_MOLECULE_STARTUP_TIME, PER_MOLECULE_GAP


class TestUserRequestTotalDuration(ConfigDBTestMixin, SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        semester = mixer.blend(Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
                               end=datetime(2016, 12, 31, tzinfo=timezone.utc)
                               )
        self.time_allocation_1m0 = mixer.blend(TimeAllocation, proposal=self.proposal, semester=semester,
                                               telescope_class='1m0', std_allocation=100.0, std_time_used=0.0,
                                               too_allocation=10, too_time_used=0.0, ipp_limit=10.0,
                                               ipp_time_available=5.0)

        self.ur_single = mixer.blend(UserRequest, proposal=self.proposal, operator='SINGLE')
        self.ur_many = mixer.blend(UserRequest, proposal=self.proposal)

        self.request = mixer.blend(Request, user_request=self.ur_single)
        self.requests = mixer.cycle(3).blend(Request, user_request=self.ur_many)

        self.molecule_expose = mixer.blend(
            Molecule, request=self.request, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=600, exposure_count=2, type='EXPOSE', filter='blah'
        )

        self.molecule_exposes = mixer.cycle(3).blend(
            Molecule, request=(r for r in self.requests), filter=(f for f in ['uv', 'uv', 'ir']),
            bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG', exposure_time=1000, exposure_count=1, type='EXPOSE'
        )

        mixer.blend(
            Window, request=self.request, start=datetime(2016, 9, 29, tzinfo=timezone.utc),
            end=datetime(2016, 10, 29, tzinfo=timezone.utc)
        )
        mixer.cycle(3).blend(
            Window, request=(r for r in self.requests), start=datetime(2016, 9, 29, tzinfo=timezone.utc),
            end=datetime(2016, 10, 29, tzinfo=timezone.utc)
        )

        mixer.blend(Target, request=self.request)
        mixer.cycle(3).blend(Target, request=(r for r in self.requests))

        mixer.blend(Location, request=self.request, telescope_class='1m0')
        mixer.cycle(3).blend(Location, request=(r for r in self.requests), telescope_class='1m0')

        mixer.blend(Constraints, request=self.request)
        mixer.cycle(3).blend(Constraints, request=(r for r in self.requests))

    def test_single_ur_total_duration(self):
        request_duration = self.request.duration
        total_duration = self.ur_single.total_duration
        tak = self.request.time_allocation_key
        self.assertEqual(request_duration, total_duration[tak])

    def test_many_ur_takes_highest_duration(self):
        self.ur_many.operator = 'MANY'
        self.ur_many.save()

        highest_duration = max(r.duration for r in self.requests)
        total_duration = self.ur_many.total_duration
        tak = self.requests[0].time_allocation_key
        self.assertEqual(highest_duration, total_duration[tak])

    def test_and_ur_takes_sum_of_durations(self):
        self.ur_many.operator = 'AND'
        self.ur_many.save()

        sum_duration = sum(r.duration for r in self.requests)
        total_duration = self.ur_many.total_duration
        tak = self.requests[0].time_allocation_key
        self.assertEqual(sum_duration, total_duration[tak])


class TestRequestDuration(ConfigDBTestMixin, SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.request = mixer.blend(Request)
        mixer.blend(Target, request=self.request)
        mixer.blend(Location, request=self.request)
        mixer.blend(Constraints, request=self.request)
        self.target_acquire_on = mixer.blend(Target, acquire_mode='ON', type='SIDEREAL')

        self.target_acquire_off = mixer.blend(Target, acquire_mode='OFF', type='SIDEREAL')

        self.molecule_expose = mixer.blend(
            Molecule, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=600, exposure_count=2, type='EXPOSE', filter='blah'
        )

        self.molecule_expose_1 = mixer.blend(
            Molecule, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=1000, exposure_count=1, type='EXPOSE', filter='uv'
        )

        self.molecule_expose_2 = mixer.blend(
            Molecule, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=10, exposure_count=5, type='EXPOSE', filter='uv'
        )

        self.molecule_expose_3 = mixer.blend(
            Molecule, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=3, exposure_count=3, type='EXPOSE', filter='ir'
        )

        self.molecule_spectrum = mixer.blend(
            Molecule, bin_x=1, bin_y=1, instrument_name='2M0-FLOYDS-SCICAM',
            exposure_time=1800, exposure_count=1, type='SPECTRUM'
        )

        self.molecule_arc = mixer.blend(
            Molecule, bin_x=1, bin_y=1, instrument_name='2M0-FLOYDS-SCICAM',
            exposure_time=30, exposure_count=2, type='ARC'
        )

        self.molecule_lampflat = mixer.blend(
            Molecule, bin_x=1, bin_y=1, instrument_name='2M0-FLOYDS-SCICAM',
            exposure_time=60, exposure_count=1, type='LAMPFLAT'
        )

        self.sbig_fixed_overhead_per_exposure = 1
        self.sbig_filter_change_time = 2
        self.sbig_front_padding = 90
        self.sbig_readout_time2 = 14.5

        self.floyds_fixed_overhead_per_exposure = 0.5
        self.floyds_filter_change_time = 0
        self.floyds_front_padding = 240
        self.floyds_readout_time1 = 25
        self.floyds_config_change_time = 30
        self.floyds_acquire_processing_time = 60
        self.floyds_acquire_exposure_time = 30


    def test_ccd_single_molecule_request_duration(self):
        self.molecule_expose.request = self.request
        self.molecule_expose.save()
        duration = self.request.duration

        exp_time = self.molecule_expose.exposure_time
        exp_count = self.molecule_expose.exposure_count

        self.assertEqual(duration, math.ceil(exp_count*(exp_time + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure) + self.sbig_front_padding + self.sbig_filter_change_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME))

    def test_ccd_single_molecule_unsupported_binning_duration(self):
        default_binning = mixer.blend(
            Molecule, bin_x=2, bin_y=2, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=600, exposure_count=2, type='EXPOSE', filter='blah'
        )

        bad_binning = mixer.blend(
            Molecule, bin_x=300, bin_y=300, instrument_name='1M0-SCICAM-SBIG',
            exposure_time=600, exposure_count=2, type='EXPOSE', filter='blah'
        )

        self.assertEqual(default_binning.duration, bad_binning.duration)

    def test_ccd_single_molecule_duration(self):
        duration = self.molecule_expose.duration

        exp_time = self.molecule_expose.exposure_time
        exp_count = self.molecule_expose.exposure_count

        self.assertEqual(duration, (exp_count*(exp_time + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure) + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME))

    def test_ccd_multiple_molecule_request_duration(self):
        self.molecule_expose_1.request = self.request
        self.molecule_expose_1.save()
        self.molecule_expose_2.request = self.request
        self.molecule_expose_2.save()
        self.molecule_expose_3.request = self.request
        self.molecule_expose_3.save()
        duration = self.request.duration

        exp_time1 = self.molecule_expose_1.exposure_time
        exp_count1 = self.molecule_expose_1.exposure_count
        exp_time2 = self.molecule_expose_2.exposure_time
        exp_count2 = self.molecule_expose_2.exposure_count
        exp_time3 = self.molecule_expose_3.exposure_time
        exp_count3 = self.molecule_expose_3.exposure_count

        exp_1_duration = exp_count1*(exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2*(exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3*(exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)

        num_filter_changes = 2
        num_molecules = 3

        self.assertEqual(duration, math.ceil(exp_1_duration + exp_2_duration + exp_3_duration + self.sbig_front_padding + num_filter_changes*self.sbig_filter_change_time + num_molecules*(PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))

    def test_ccd_multiple_molecule_duration(self):
        duration = self.molecule_expose_1.duration
        duration += self.molecule_expose_2.duration
        duration += self.molecule_expose_3.duration

        exp_time1 = self.molecule_expose_1.exposure_time
        exp_count1 = self.molecule_expose_1.exposure_count
        exp_time2 = self.molecule_expose_2.exposure_time
        exp_count2 = self.molecule_expose_2.exposure_count
        exp_time3 = self.molecule_expose_3.exposure_time
        exp_count3 = self.molecule_expose_3.exposure_count

        exp_1_duration = exp_count1 * (exp_time1 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_2_duration = exp_count2 * (exp_time2 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)
        exp_3_duration = exp_count3 * (exp_time3 + self.sbig_readout_time2 + self.sbig_fixed_overhead_per_exposure)

        num_molecules = 3

        self.assertEqual(duration, (exp_1_duration + exp_2_duration + exp_3_duration + num_molecules*(PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))

    def test_floyds_single_molecule_request_duration_with_acquire_on(self):
        self.molecule_spectrum.request = self.request
        self.molecule_spectrum.acquire_mode = 'WCS'
        self.molecule_spectrum.save()

        duration = self.request.duration

        exp_time = 1800
        exp_count = 1

        self.assertEqual(duration, math.ceil(exp_count*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + self.floyds_front_padding + self.floyds_config_change_time + self.floyds_acquire_exposure_time + self.floyds_acquire_processing_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME))

    def test_floyds_multiple_spectrum_molecule_request_duration_with_acquire_on(self):
        self.molecule_spectrum.request = self.request
        self.molecule_spectrum.acquire_mode = 'WCS'
        self.molecule_spectrum.save()

        mixer.blend(
            Molecule, request=self.request, bin_x=1, bin_y=1, instrument_name='2M0-FLOYDS-SCICAM',
            exposure_time=1800, exposure_count=1, type='SPECTRUM', acquire_mode='WCS'
        )

        duration = self.request.duration

        exp_time = 1800
        exp_count = 1
        num_spectrum_molecules = 2

        self.assertEqual(duration, math.ceil(exp_count*num_spectrum_molecules*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + self.floyds_front_padding + self.floyds_config_change_time + num_spectrum_molecules*(self.floyds_acquire_exposure_time + self.floyds_acquire_processing_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))


    def test_floyds_single_molecule_request_duration_with_acquire_off(self):
        self.molecule_spectrum.request = self.request
        self.molecule_spectrum.save()

        duration = self.request.duration

        exp_time = self.molecule_spectrum.exposure_time
        exp_count = self.molecule_spectrum.exposure_count

        self.assertEqual(duration, math.ceil(exp_count*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + self.floyds_front_padding + self.floyds_config_change_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME))

    def test_floyds_single_molecule_duration(self):
        duration = self.molecule_spectrum.duration

        exp_time = self.molecule_spectrum.exposure_time
        exp_count = self.molecule_spectrum.exposure_count

        self.assertEqual(duration, (exp_count*(exp_time + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure) + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME))

    def test_floyds_multiple_molecule_request_duration_with_acquire_on(self):
        self.molecule_lampflat.request = self.request
        self.molecule_lampflat.save()
        self.molecule_arc.request = self.request
        self.molecule_arc.save()
        self.molecule_spectrum.request = self.request
        self.molecule_spectrum.acquire_mode = 'WCS'
        self.molecule_spectrum.save()

        duration = self.request.duration

        exp_time_s = self.molecule_spectrum.exposure_time
        exp_count_s = self.molecule_spectrum.exposure_count
        exp_time_a = self.molecule_arc.exposure_time
        exp_count_a = self.molecule_arc.exposure_count
        exp_time_l = self.molecule_lampflat.exposure_time
        exp_count_l = self.molecule_lampflat.exposure_count

        exp_s_duration = exp_count_s*(exp_time_s + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_a_duration = exp_count_a*(exp_time_a + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_l_duration = exp_count_l*(exp_time_l + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)

        num_molecules = 3

        self.assertEqual(duration, math.ceil(exp_s_duration + exp_a_duration + exp_l_duration + self.floyds_front_padding + self.floyds_acquire_exposure_time + self.floyds_acquire_processing_time + num_molecules*(self.floyds_config_change_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))

    def test_floyds_multiple_molecule_request_duration_with_acquire_off(self):
        self.molecule_lampflat.request = self.request
        self.molecule_lampflat.save()
        self.molecule_arc.request = self.request
        self.molecule_arc.save()
        self.molecule_spectrum.request = self.request
        self.molecule_spectrum.save()

        duration = self.request.duration

        exp_time_s = self.molecule_spectrum.exposure_time
        exp_count_s = self.molecule_spectrum.exposure_count
        exp_time_a = self.molecule_arc.exposure_time
        exp_count_a = self.molecule_arc.exposure_count
        exp_time_l = self.molecule_lampflat.exposure_time
        exp_count_l = self.molecule_lampflat.exposure_count

        exp_s_duration = exp_count_s*(exp_time_s + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_a_duration = exp_count_a*(exp_time_a + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_l_duration = exp_count_l*(exp_time_l + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)

        num_molecules = 3

        self.assertEqual(duration, math.ceil(exp_s_duration + exp_a_duration + exp_l_duration + self.floyds_front_padding + num_molecules*(self.floyds_config_change_time + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))

    def test_floyds_multiple_molecule_duration(self):
        duration = self.molecule_lampflat.duration
        duration += self.molecule_arc.duration
        duration += self.molecule_spectrum.duration

        exp_time_s = self.molecule_spectrum.exposure_time
        exp_count_s = self.molecule_spectrum.exposure_count
        exp_time_a = self.molecule_arc.exposure_time
        exp_count_a = self.molecule_arc.exposure_count
        exp_time_l = self.molecule_lampflat.exposure_time
        exp_count_l = self.molecule_lampflat.exposure_count

        exp_s_duration = exp_count_s*(exp_time_s + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_a_duration = exp_count_a*(exp_time_a + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)
        exp_l_duration = exp_count_l*(exp_time_l + self.floyds_readout_time1 + self.floyds_fixed_overhead_per_exposure)

        num_molecules = 3

        self.assertEqual(duration, (exp_s_duration + exp_a_duration + exp_l_duration + num_molecules*(PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME)))

    def test_get_duration_from_non_existent_camera(self):
        bad_molecule = mixer.blend(Molecule, instrument_name='FAKE_INSTRUMENT', bin_x=1, bin_y=1)

        with self.assertRaises(ConfigDBException) as context:
            bad_molecule.duration
            self.assertTrue('not found in configdb' in context.exception)
