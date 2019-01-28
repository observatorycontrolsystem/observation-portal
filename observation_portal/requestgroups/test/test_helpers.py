from django.test import TestCase

from observation_portal.requestgroups.target_helpers import (SiderealTargetHelper, NonSiderealTargetHelper,
                                                             SatelliteTargetHelper)


class TestTargetHelper(TestCase):
    def setUp(self):
        self.target = {
            'acquire_mode': 'OPTIONAL',
            'altitude': 45.0,
            'argofperih': 180.0,
            'azimuth': 180.0,
            'coordinate_system': 'ICRS',
            'dailymot': 0,
            'dec': 45,
            'diff_epoch_rate': 0,
            'diff_pitch_acceleration': 0,
            'diff_pitch_rate': 0,
            'diff_roll_acceleration': 0,
            'diff_roll_rate': 0,
            'eccentricity': 0.5,
            'epoch': 2000.0,
            'epochofel': 10000,
            'epochofperih': 10000,
            'equinox': 'J2000',
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
            'pitch': 0,
            'proper_motion_dec': 0,
            'proper_motion_ra': 0,
            'ra': 180.0,
            'roll': 0,
            'scheme': '',
            'type': 'SIDEREAL'
        }

    def test_sidereal_helper_fields(self):
        sth = SiderealTargetHelper(self.target)
        self.assertFalse('scheme' in sth.data)
        self.assertFalse('diff_roll_rate' in sth.data)
        self.assertTrue('ra' in sth.data)

    def test_nonsidereal_helper_fields(self):
        nsh = NonSiderealTargetHelper(self.target)
        self.assertFalse('ra' in nsh.data)
        self.assertFalse('diff_pitch_rate' in nsh.data)
        self.assertTrue('scheme' in nsh.data)

    def test_satellite_helper_fields(self):
        sh = SatelliteTargetHelper(self.target)
        self.assertFalse('ra' in sh.data)
        self.assertFalse('scheme' in sh.data)
        self.assertTrue('diff_roll_rate' in sh.data)

    def test_sidereal_target_required(self):
        bad_data = self.target.copy()
        del bad_data['ra']
        sth = SiderealTargetHelper(bad_data)
        self.assertFalse(sth.is_valid())

    def test_nonsideral_target_required(self):
        bad_data = self.target.copy()
        del bad_data['scheme']
        nsh = NonSiderealTargetHelper(bad_data)
        self.assertFalse(nsh.is_valid())

    def test_satellite_target_required(self):
        bad_data = self.target.copy()
        del bad_data['diff_pitch_rate']
        sh = SatelliteTargetHelper(bad_data)
        self.assertFalse(sh.is_valid())

    def test_sidereal_target_default(self):
        bad_data = self.target.copy()
        del bad_data['coordinate_system']
        sth = SiderealTargetHelper(bad_data)
        self.assertEqual(sth.data['coordinate_system'], 'ICRS')
