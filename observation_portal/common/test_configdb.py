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

    def test_get_telescope_key(self):
        expected_key1 = TelescopeKey('tst', 'doma', '2m0a', '2m0')
        key1 = configdb.get_telescope_key('tst', 'doma', '2m0a')
        self.assertEqual(key1, expected_key1)
        self.assertEqual(key1.telescope_class, expected_key1.telescope_class)

        expected_key2 = TelescopeKey('tst', 'domb', '1m0a', '1m0')
        key2 = configdb.get_telescope_key('tst', 'domb', '1m0a')
        self.assertEqual(key2, expected_key2)
        self.assertEqual(key2.telescope_class, expected_key2.telescope_class)

        # Test for a non-existent telescope class
        expected_key3 = TelescopeKey('tst', 'doma', '3m0a', 'N/A')
        key3 = configdb.get_telescope_key('tst', 'doma', '3m0a')
        self.assertEqual(key3, expected_key3)
        self.assertEqual(key3.telescope_class, expected_key3.telescope_class)
