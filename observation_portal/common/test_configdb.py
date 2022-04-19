from django.test import TestCase

from observation_portal.common.configdb import configdb, TelescopeKey


class TestConfigdb(TestCase):
    def test_convert_telescope_aperture_to_string(self):
        expected_telescope_class1 = '1m0'
        telescope_class1 = configdb.convert_telescope_aperture_to_string(1.0)
        self.assertEqual(expected_telescope_class1, telescope_class1)

        expected_telescope_class2 = '0m4'
        telescope_class2 = configdb.convert_telescope_aperture_to_string(0.44)
        self.assertEqual(expected_telescope_class2, telescope_class2)
        
        expected_telescope_class3 = '2m1'
        telescope_class3 = configdb.convert_telescope_aperture_to_string(2.124)
        self.assertEqual(expected_telescope_class3, telescope_class3)
        
        expected_telescope_class4 = '33m2'
        telescope_class4 = configdb.convert_telescope_aperture_to_string(33.16)
        self.assertEqual(expected_telescope_class4, telescope_class4)
        
        expected_telescope_class5 = '0m0'
        telescope_class5 = configdb.convert_telescope_aperture_to_string(0.0)
        self.assertEqual(expected_telescope_class5, telescope_class5)
        