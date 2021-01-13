from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from observation_portal.accounts.test_utils import blend_user
from observation_portal.common.telescope_states import ElasticSearchException
from observation_portal.common.test_telescope_states import TelescopeStatesFromFile


class TestTelescopeStates(TelescopeStatesFromFile):
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.client.force_login(self.user)

    def test_date_format_1(self):
        response = self.client.get(reverse('api:telescope_states') + '?start=2016-10-1&end=2016-10-10')
        self.assertContains(response, "lsc")

    def test_date_format_2(self):
        response = self.client.get(reverse('api:telescope_availability') +
                                   '?start=2016-10-1T1:23:44&end=2016-10-10T22:22:2')
        self.assertContains(response, "lsc")

    def test_date_format_bad(self):
        response = self.client.get(reverse('api:telescope_states') +
                                   '?start=2016-10-1%201:3323:44&end=10-10T22:22:2')
        self.assertEqual(response.status_code, 400)
        self.assertIn("minute must be in 0..59", str(response.content))

    def test_no_date_specified(self):
        response = self.client.get(reverse('api:telescope_states'))
        self.assertContains(response, str(timezone.now().date()))

    @patch('observation_portal.common.telescope_states.TelescopeStates._get_es_data', side_effect=ElasticSearchException)
    def test_elasticsearch_down(self, es_patch):
        response = self.client.get(reverse('api:telescope_availability') +
                                   '?start=2016-10-1T1:23:44&end=2016-10-10T22:22:2')
        self.assertContains(response, 'ConnectionError')


class TestInstrumentInformation(TestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = blend_user(user_params={'is_staff': True})

    def test_instrument_information(self):
        response = self.client.get(reverse('api:instruments_information'))
        self.assertIn('1M0-SCICAM-SBIG', response.json())

    def test_instrument_information_for_specific_telescope(self):
        response = self.client.get(reverse('api:instruments_information') + '?telescope=2m0a')
        self.assertIn('2M0-FLOYDS-SCICAM', response.json())
        self.assertNotIn('1M0-SCICAM-SBIG', response.json())

    def test_instrument_information_for_nonexistent_location(self):
        response = self.client.get(reverse('api:instruments_information') + '?site=idontexist')
        self.assertEqual(len(response.json()), 0)

    def test_instrument_information_for_specific_instrument_type(self):
        response = self.client.get(reverse('api:instruments_information') + '?instrument_type=1M0-SCICAM-SBIG')
        self.assertEqual(len(response.json()), 1)
        self.assertIn('1M0-SCICAM-SBIG', response.json())

    def test_non_staff_user_can_only_see_schedulable(self):
        response = self.client.get(reverse('api:instruments_information') + '?only_schedulable=false')
        self.assertNotIn('1M0-SCICAM-SBXX', response.json())

    def test_staff_user_can_see_non_schedulable_by_default(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:instruments_information'))
        self.assertIn('1M0-SCICAM-SBXX', response.json())

    def test_staff_user_can_request_only_schedulable(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:instruments_information') + '?only_schedulable=true')
        self.assertNotIn('1M0-SCICAM-SBXX', response.json())
