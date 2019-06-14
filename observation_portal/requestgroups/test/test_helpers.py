from django.test import TestCase

from observation_portal.requestgroups.target_helpers import (ICRSTargetHelper, OrbitalElementsTargetHelper,
                                                             SatelliteTargetHelper)


class TestTargetHelper(TestCase):
    def setUp(self):
        self.target = {
            'acquire_mode': 'OPTIONAL',
            'altitude': 45.0,
            'argofperih': 180.0,
            'azimuth': 180.0,
            'dailymot': 0,
            'dec': 45,
            'diff_epoch': 0,
            'diff_altitude_acceleration': 0,
            'diff_altitude_rate': 0,
            'diff_azimuth_acceleration': 0,
            'diff_azimuth_rate': 0,
            'eccentricity': 0.5,
            'epoch': 2000.0,
            'epochofel': 10000,
            'epochofperih': 10000,
            'hour_angle': 0,
            'longascnode': 0,
            'longofperih': 0,
            'meananom': 0,
            'meandist': 0,
            'meanlong': 0,
            'name': 'Planet X',
            'orbinc': 45.0,
            'parallax': 0,
            'perihdist': 0,
            'proper_motion_dec': 0,
            'proper_motion_ra': 0,
            'ra': 180.0,
            'scheme': '',
            'type': 'ICRS'
        }

    def test_icrs_helper_fields(self):
        sth = ICRSTargetHelper(self.target)
        self.assertFalse('scheme' in sth.data)
        self.assertFalse('diff_azimuth_rate' in sth.data)
        self.assertTrue('ra' in sth.data)

    def test_orbital_elements_helper_fields(self):
        nsh = OrbitalElementsTargetHelper(self.target)
        self.assertFalse('ra' in nsh.data)
        self.assertFalse('diff_altitude_rate' in nsh.data)
        self.assertTrue('scheme' in nsh.data)

    def test_satellite_helper_fields(self):
        sh = SatelliteTargetHelper(self.target)
        self.assertFalse('ra' in sh.data)
        self.assertFalse('scheme' in sh.data)
        self.assertTrue('diff_azimuth_rate' in sh.data)

    def test_icrs_target_required(self):
        bad_data = self.target.copy()
        del bad_data['ra']
        sth = ICRSTargetHelper(bad_data)
        self.assertFalse(sth.is_valid())

    def test_orbital_elements_target_required(self):
        bad_data = self.target.copy()
        del bad_data['scheme']
        nsh = OrbitalElementsTargetHelper(bad_data)
        self.assertFalse(nsh.is_valid())

    def test_satellite_target_required(self):
        bad_data = self.target.copy()
        del bad_data['diff_altitude_rate']
        sh = SatelliteTargetHelper(bad_data)
        self.assertFalse(sh.is_valid())

