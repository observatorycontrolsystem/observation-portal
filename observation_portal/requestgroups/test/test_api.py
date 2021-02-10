from observation_portal.requestgroups.models import (RequestGroup, Request, DraftRequestGroup, Window, Target,
                                                     Configuration, Location, Constraints, InstrumentConfig,
                                                     AcquisitionConfig, GuidingConfig)
from observation_portal.proposals.models import Proposal, Membership, TimeAllocation, Semester
from observation_portal.observations.models import Observation, ConfigurationStatus
from observation_portal.common.test_helpers import SetTimeMixin, create_simple_requestgroup
import observation_portal.requestgroups.signals.handlers  # noqa

# imports for cache based tests
import observation_portal.observations.signals.handlers  # noqa
from observation_portal.requestgroups import serializers
from observation_portal.requestgroups import views
from observation_portal.common import state_changes
from observation_portal.common.test_helpers import create_simple_configuration

from observation_portal.requestgroups.contention import Pressure
from observation_portal.accounts.test_utils import blend_user

from django.urls import reverse
from django.core import cache
from dateutil.parser import parse as datetime_parser
from rest_framework.test import APITestCase
from mixer.backend.django import mixer
from django.utils import timezone
from datetime import datetime, timedelta
import copy
import random
from unittest.mock import patch

generic_payload = {
    'proposal': 'temp',
    'name': 'test group',
    'operator': 'SINGLE',
    'ipp_value': 1.0,
    'observation_type': 'NORMAL',
    'requests': [{
        'configurations': [{
            'type': 'EXPOSE',
            'instrument_type': '1M0-SCICAM-SBIG',
            'target': {
                'name': 'fake target',
                'type': 'ICRS',
                'dec': 20,
                'ra': 34.4,
            },
            'instrument_configs': [{
                'exposure_time': 100,
                'exposure_count': 1,
                'mode': '',
                'bin_x': 1,
                'bin_y': 1,
                'optical_elements': {
                    'filter': 'air'
                }
            }],
            'guiding_config': {
                'extra_params': {}
            },
            'acquisition_config': {
                'extra_params': {}
            },
            'constraints': {
                'max_airmass': 2.0,
                'min_lunar_distance': 30.0,
            }
        }],
        'windows': [{
            'start': '2016-09-29T21:12:18Z',
            'end': '2016-10-29T21:12:19Z'
        }],
        'location': {
            'telescope_class': '1m0',
        },
    }]
}


class TestUserGetRequestApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user(user_params={'is_staff': False, 'is_superuser': False})
        self.other_user = blend_user(user_params={'is_staff': False, 'is_superuser': False})
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.staff_user = blend_user(user_params={'is_staff': True})

    def test_get_request_group_detail_unauthenticated(self):
        self.client.force_login(self.other_user)
        request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup",
                                    observation_type=RequestGroup.NORMAL)
        result = self.client.get(reverse('api:request_groups-detail', args=(request_group.id,)))
        self.assertEqual(result.status_code, 404)

    def test_get_request_group_detail_authenticated(self):
        request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup",
                                    observation_type=RequestGroup.NORMAL)
        self.client.force_login(self.user)
        result = self.client.get(reverse('api:request_groups-detail', args=(request_group.id,)))
        self.assertContains(result, request_group.name)

    def test_get_request_group_list_unauthenticated(self):
        self.client.force_login(self.other_user)
        mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup",
                    observation_type=RequestGroup.NORMAL)
        result = self.client.get(reverse('api:request_groups-list'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['results'], [])

    def test_get_request_group_list_authenticated(self):
        request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup",
                                    observation_type=RequestGroup.NORMAL)
        self.client.force_login(self.user)
        result = self.client.get(reverse('api:request_groups-list'))
        self.assertContains(result, request_group.name)

    def test_get_request_group_list_is_staff_without_staff_view(self):
        mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup2",
                    observation_type=RequestGroup.NORMAL)
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:request_groups-list'))
        self.assertEqual(len(result.json()['results']), 0)

    def test_get_request_group_list_staff_with_staff_view(self):
        self.staff_user.profile.staff_view = True
        self.staff_user.profile.save()
        request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup2",
                                    observation_type=RequestGroup.NORMAL)
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:request_groups-list'))
        self.assertContains(result, request_group.name)

    def test_requestgroup_list_view_authored_requests_only(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        request_group_authored = mixer.blend(
            RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup1",
            observation_type=RequestGroup.NORMAL
        )
        mixer.blend(Membership, user=self.other_user, proposal=self.proposal)
        request_group_not_authored = mixer.blend(
            RequestGroup, submitter=self.other_user, proposal=self.proposal, name="testgroup2",
            observation_type=RequestGroup.NORMAL
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:request_groups-list'))
        self.assertContains(response, request_group_authored.name)
        self.assertNotContains(response, request_group_not_authored.name)

    def test_requestgroup_detail_is_staff_without_staff_view(self):
        request_group = mixer.blend(
            RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup1",
            observation_type=RequestGroup.NORMAL
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:request_groups-detail', args=(request_group.id,)))
        self.assertEqual(response.status_code, 404)

    def test_requestgroup_detail_is_staff_with_staff_view_enabled(self):
        self.staff_user.profile.staff_view = True
        self.staff_user.profile.save()
        request_group = mixer.blend(
            RequestGroup, submitter=self.user, proposal=self.proposal, name="testgroup1",
            observation_type=RequestGroup.NORMAL
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:request_groups-detail', args=(request_group.id,)))
        self.assertContains(response, request_group.name)

    def test_get_request_group_detail_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        authored_request_group = mixer.blend(
            RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.user,
            observation_type=RequestGroup.NORMAL
        )
        mixer.blend(Membership, user=self.other_user, proposal=self.proposal)
        non_authored_request_group = mixer.blend(
            RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.other_user,
            observation_type=RequestGroup.NORMAL
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:request_groups-detail', args=(non_authored_request_group.id,)))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('api:request_groups-detail', args=(authored_request_group.id,)))
        self.assertContains(response, authored_request_group.name)

    def test_requestgroups_list_dont_include_other_proposals(self):
        self.client.force_login(self.user)
        proposal = mixer.blend(Proposal)
        other_rg = mixer.blend(RequestGroup, proposal=proposal, name=mixer.RANDOM, observation_type=RequestGroup.NORMAL)
        response = self.client.get(reverse('api:request_groups-list'))
        self.assertNotContains(response, other_rg.name)

    def test_get_request_group_detail_public(self):
        proposal = mixer.blend(Proposal, public=True)
        request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=proposal, name="publicgroup",
                                    observation_type=RequestGroup.NORMAL)
        result = self.client.get(reverse('api:request_groups-detail', args=(request_group.id,)))
        self.assertContains(result, request_group.name)


class TestUserPostRequestApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )
        self.time_allocation_2m0_floyds = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='2M0-FLOYDS-SCICAM', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )
        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id

    def test_post_requestgroup_unauthenticated(self):
        self.other_user = blend_user()
        self.client.force_login(self.other_user)
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_authenticated(self):
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], self.generic_payload['name'])

    def test_post_requestgroup_wrong_proposal(self):
        bad_data = self.generic_payload.copy()
        bad_data['proposal'] = 'DoesNotExist'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_no_membership(self):
        proposal = mixer.blend(Proposal)
        bad_data = self.generic_payload.copy()
        bad_data['proposal'] = proposal.id
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('You do not belong', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_missing_data(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_no_configurations(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'] = []
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_no_requests(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'] = []
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_no_time_allocation_for_instrument(self):
        self.time_allocation_2m0_floyds.delete()
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['telescope_class'] = '2m0'
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('You do not have sufficient NORMAL time', str(response.content))

    def test_post_requestgroup_manual_instrument_not_allowed(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = 'tst'
        bad_data['requests'][0]['location']['enclosure'] = 'domc'
        bad_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid instrument type', str(response.content))

    def test_post_requestgroup_manual_instrument_not_allowed_with_staff_without_full_location(self):
        eng_user = blend_user(user_params={'username': 'eng', 'is_staff': True})
        mixer.blend(Membership, user=eng_user, proposal=self.proposal)
        self.client.force_login(eng_user)
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = 'tst'
        bad_data['requests'][0]['location']['enclosure'] = 'domc'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid instrument type', str(response.content))

    def test_post_requestgroup_manual_instrument_allowed_for_staff(self):
        good_data = self.generic_payload.copy()
        eng_user = blend_user(user_params={'username': 'eng', 'is_staff': True})
        mixer.blend(Membership, user=eng_user, proposal=self.proposal)
        self.client.force_login(eng_user)
        good_data['requests'][0]['location']['site'] = 'tst'
        good_data['requests'][0]['location']['enclosure'] = 'domc'
        good_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_not_enough_time_allocation_for_instrument(self):
        bad_data = self.generic_payload.copy()
        self.time_allocation_1m0_sbig.std_time_used = 99.99
        self.time_allocation_1m0_sbig.save()
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('does not have enough NORMAL time allocated', str(response.content))

    def test_post_requestgroup_not_enough_rr_time_allocation_for_instrument(self):
        bad_data = self.generic_payload.copy()
        bad_data['observation_type'] = RequestGroup.RAPID_RESPONSE
        bad_data['requests'][0]['windows'][0]['start'] = '2016-09-01T00:00:00Z'
        bad_data['requests'][0]['windows'][0]['end'] = '2016-09-01T05:59:59Z'
        self.time_allocation_1m0_sbig.rr_time_used = 9.99
        self.time_allocation_1m0_sbig.save()
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('does not have enough RAPID_RESPONSE time allocated', str(response.content))

    def test_post_requestgroup_rr_future_start_time(self):
        bad_data = self.generic_payload.copy()
        bad_data['observation_type'] = RequestGroup.RAPID_RESPONSE
        bad_data['requests'][0]['windows'][0]['start'] = timezone.now() + timedelta(0, 60)
        bad_data['requests'][0]['windows'][0]['end'] = timezone.now() + timedelta(0, 18000)
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot be in the future.', str(response.content))

    def test_post_requestgroup_rr_within_24_hours(self):
        data = self.generic_payload.copy()
        data['observation_type'] = RequestGroup.RAPID_RESPONSE
        data['requests'][0]['windows'][0]['start'] = timezone.now() + timedelta(0)
        data['requests'][0]['windows'][0]['end'] = timezone.now() + timedelta(0, 82800)  # 23 hours
        response = self.client.post(reverse('api:request_groups-list'), data=data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_rr_not_within_24_hours(self):
        bad_data = self.generic_payload.copy()
        bad_data['observation_type'] = RequestGroup.RAPID_RESPONSE
        bad_data['requests'][0]['windows'][0]['start'] = timezone.now() + timedelta(0)
        bad_data['requests'][0]['windows'][0]['end'] = timezone.now() + timedelta(0, 90000)  # 25 hours
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('must start within the next 24 hours', str(response.content))

    def test_post_requestgroup_not_have_any_time_left(self):
        bad_data = self.generic_payload.copy()
        self.time_allocation_1m0_sbig.std_time_used = 120
        self.time_allocation_1m0_sbig.save()
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('does not have any NORMAL time left allocated', str(response.content))

    def test_post_requestgroup_time_limit_reached(self):
        self.membership.time_limit = 0
        self.membership.save()
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('duration will exceed the time limit set for your account ', str(response.content))

    def test_post_requestgroup_time_limit_not_reached(self):
        self.membership.time_limit = 1000
        self.membership.save()
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_bad_ipp(self):
        bad_data = self.generic_payload.copy()
        bad_data['ipp_value'] = 0.0
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_default_acquire_mode(self):
        good_data = self.generic_payload.copy()
        # verify default acquire mode is 'off' for non-floyds
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['acquisition_config']['mode'], 'OFF')

        # check that default acquire mode is 'wcs' for floyds
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['acquisition_config']['mode'], 'WCS')
        # Check that default acquire mode is OFF for floyds non-spectrum
        good_data['requests'][0]['configurations'][0]['type'] = 'LAMP_FLAT'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['acquisition_config']['mode'], 'OFF')

    def test_post_requestgroup_acquire_mode_brightest_no_radius(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['telescope_class'] = '2m0'
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['acquisition_config']['mode'] = 'BRIGHTEST'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Acquisition mode BRIGHTEST requirements are not met: extra_params{acquire_radius error: required field}', str(response.content))

    def test_post_requestgroup_acquire_mode_brightest(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        good_data['requests'][0]['configurations'][0]['acquisition_config']['mode'] = 'BRIGHTEST'
        good_data['requests'][0]['configurations'][0]['acquisition_config']['extra_params']['acquire_radius'] = 2
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_single_must_have_one_request(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'].append(bad_data['requests'][0].copy())
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('must have exactly one child request', str(response.content))

    # Removed AND operator for now, so commenting out this test
    # def test_post_requestgroup_and_must_have_greater_than_one_request(self):
    #     bad_data = self.generic_payload.copy()
    #     bad_data['operator'] = 'AND'
    #     response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
    #     self.assertEqual(response.status_code, 400)
    #     self.assertIn('must have more than one child request', str(response.content))

    def test_post_requestgroup_constraints_optional(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['target']['dec'] = -30.0
        good_data['requests'][0]['configurations'][0]['target']['ra'] = 50.0
        del good_data['requests'][0]['configurations'][0]['constraints']['max_airmass']
        del good_data['requests'][0]['configurations'][0]['constraints']['min_lunar_distance']
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_validation(self):
        good_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-validate'), data=good_data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['errors'])

    def test_validation_fail(self):
        bad_data = self.generic_payload.copy()
        del bad_data['operator']
        response = self.client.post(reverse('api:request_groups-validate'), data=bad_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['errors']['operator'][0], 'This field is required.')

    def test_post_requestgroup_duration_too_long(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = 999999999999
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('the target is visible for a maximum of', str(response.content))

    def test_post_requestgroup_default_acceptability_threshold(self):
        data = self.generic_payload.copy()
        # Test that default threshold for non-floyds is 90
        response = self.client.post(reverse('api:request_groups-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['acceptability_threshold'], 90)
        # Test that default threshold for floyds is 100
        data['requests'][0]['location']['telescope_class'] = '2m0'
        data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        response = self.client.post(reverse('api:request_groups-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['acceptability_threshold'], 100)


class TestDisallowedMethods(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.rg = mixer.blend(RequestGroup, proposal=self.proposal, observation_type=RequestGroup.NORMAL)
        self.client.force_login(self.user)

    def test_cannot_delete_rg(self):
        response = self.client.delete(reverse('api:request_groups-detail', args=(self.rg.id,)))
        self.assertEqual(response.status_code, 405)

    def test_cannot_update_rg(self):
        response = self.client.put(reverse('api:request_groups-detail', args=(self.rg.id,)))
        self.assertEqual(response.status_code, 405)


class TestRequestGroupIPP(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        mixer.blend(Membership, user=self.user, proposal=self.proposal)

        semester = mixer.blend(
            Semester,
            id='2016B',
            start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )

        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='1M0-SCICAM-SBIG',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0, tc_allocation=10, tc_time_used=0
        )

        self.time_allocation_2m0_floyds = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='2M0-FLOYDS-SCICAM',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0, tc_allocation=10, tc_time_used=0
        )

        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['ipp_value'] = 1.5
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['name'] = 'ipp_request'

        self.generic_multi_payload = copy.deepcopy(self.generic_payload)
        self.second_request = copy.deepcopy(generic_payload['requests'][0])
        self.second_request['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        self.second_request['configurations'][0]['type'] = 'SPECTRUM'
        del self.second_request['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        self.second_request['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        self.second_request['location']['telescope_class'] = '2m0'
        self.generic_multi_payload['requests'].append(self.second_request)

    def _build_request_group(self, rg_dict):
        response = self.client.post(reverse('api:request_groups-list'), data=rg_dict)
        self.assertEqual(response.status_code, 201)

        return RequestGroup.objects.get(name=rg_dict['name'])

    def test_request_group_debit_ipp_on_creation(self):
        self.assertEqual(self.time_allocation_1m0_sbig.ipp_time_available, 5.0)

        rg = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=rg)
        self.assertEqual(response.status_code, 201)

        # verify that now that the object is saved, ipp has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        duration = Request.objects.get(request_group=response.json()['id']).duration / 3600.0
        self.assertAlmostEqual(time_allocation.ipp_time_available, 5.0 - (duration * (rg['ipp_value'] - 1.0)), 5)

    def test_request_group_multi_debit_ipp_on_creation(self):
        self.assertEqual(self.time_allocation_1m0_sbig.ipp_time_available, 5.0)

        rg = self.generic_payload.copy()
        rg['operator'] = 'MANY'
        rg['requests'].append(copy.deepcopy(rg['requests'][0]))
        response = self.client.post(reverse('api:request_groups-list'), data=rg)
        self.assertEqual(response.status_code, 201)

        # verify that now that the object is saved, ipp has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        requests = Request.objects.filter(request_group=response.json()['id'])
        duration = 0.0
        for req in requests:
            duration += req.duration
        duration /= 3600.0
        self.assertAlmostEqual(time_allocation.ipp_time_available, 5.0 - (duration * (rg['ipp_value'] - 1.0)), 5)

    def test_tc_request_group_no_debit_ipp_on_creation(self):
        self.assertEqual(self.time_allocation_1m0_sbig.ipp_time_available, 5.0)

        rg = self.generic_payload.copy()
        rg['observation_type'] = RequestGroup.TIME_CRITICAL
        response = self.client.post(reverse('api:request_groups-list'), data=rg)
        self.assertEqual(response.status_code, 201)

        # verify that now that the object is saved, ipp has not been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)

    def test_request_group_credit_ipp_on_cancelation(self):
        request_group = self._build_request_group(self.generic_payload.copy())
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertLess(time_allocation.ipp_time_available, 5.0)
        request_group.state = 'CANCELED'
        request_group.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        # also verify that the child request state has changed to window_expired as well
        self.assertEqual(request_group.requests.first().state, 'CANCELED')

    def test_tc_request_group_no_credit_ipp_on_cancelation(self):
        rg = self.generic_payload.copy()
        rg['observation_type'] = RequestGroup.TIME_CRITICAL
        response = self.client.post(reverse('api:request_groups-list'), data=rg)
        request_group = RequestGroup.objects.get(id=response.json()['id'])
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        self.assertEqual(time_allocation.rr_time_used, 0.0)

        request_group.state = 'CANCELED'
        request_group.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        self.assertEqual(time_allocation.rr_time_used, 0.0)
        # also verify that the child request state has changed to window_expired as well
        self.assertEqual(request_group.requests.first().state, 'CANCELED')

    def test_request_group_credit_ipp_on_expiration(self):
        request_group = self._build_request_group(self.generic_payload.copy())
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertLess(time_allocation.ipp_time_available, 5.0)
        request_group.state = 'WINDOW_EXPIRED'
        request_group.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        # also verify that the child request state has changed to window_expired as well
        self.assertEqual(request_group.requests.first().state, 'WINDOW_EXPIRED')

    def test_request_group_debit_ipp_on_creation_fail(self):
        self.time_allocation_1m0_sbig.ipp_time_available = 0
        self.time_allocation_1m0_sbig.save()
        rg = self.generic_payload.copy()
        # ipp duration that is too high, will be rejected
        rg['ipp_value'] = 2.0
        response = self.client.post(reverse('api:request_groups-list'), data=rg)
        self.assertEqual(response.status_code, 400)
        self.assertIn('TimeAllocationError', str(response.content))
        self.assertIn('An IPP Value of 2.0 requires more IPP time than you have available', str(response.content))
        # verify that objects were not created by the send
        self.assertFalse(RequestGroup.objects.filter(name='ipp_request').exists())

    def test_request_group_multi_credit_ipp_back_on_cancelation(self):
        rg = self.generic_multi_payload
        rg['operator'] = 'MANY'
        request_group = self._build_request_group(rg)
        # verify that now that both the TimeAllocation has been debited
        time_allocation_1m0 = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertLess(time_allocation_1m0.ipp_time_available, 5.0)
        time_allocation_2m0 = TimeAllocation.objects.get(pk=self.time_allocation_2m0_floyds.id)
        self.assertLess(time_allocation_2m0.ipp_time_available, 5.0)
        # now set one request to completed, then set the user request to unschedulable
        request = request_group.requests.first()
        request.state = 'COMPLETED'
        request.save()
        request_group.state = 'WINDOW_EXPIRED'
        request_group.save()
        # now verify that time allocation 1 is still debited, but time allocation 2 has been credited back its time
        time_allocation_1m0 = TimeAllocation.objects.get(pk=self.time_allocation_1m0_sbig.id)
        self.assertLess(time_allocation_1m0.ipp_time_available, 5.0)
        time_allocation_2m0 = TimeAllocation.objects.get(pk=self.time_allocation_2m0_floyds.id)
        self.assertEqual(time_allocation_2m0.ipp_time_available, 5.0)


class TestRequestIPP(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        mixer.blend(Membership, user=self.user, proposal=self.proposal)

        semester = mixer.blend(
            Semester,
            id='2016B',
            start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc),
        )

        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )

        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['ipp_value'] = 1.5
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['name'] = 'ipp_request'

    def _build_request_group(self, rg_dict):
        response = self.client.post(reverse('api:request_groups-list'), data=rg_dict)
        self.assertEqual(response.status_code, 201)

        return RequestGroup.objects.get(name=rg_dict['name'])

    def test_request_debit_on_completion_after_expired(self):
        request_group = self._build_request_group(self.generic_payload.copy())
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        debitted_ipp_value = time_allocation.ipp_time_available
        self.assertLess(debitted_ipp_value, 5.0)
        # now change requests state to expired
        request = request_group.requests.first()
        request.state = 'WINDOW_EXPIRED'
        request.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        # now set request to completed and see that ipp is debited once more
        request.state = 'COMPLETED'
        request.save()
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, debitted_ipp_value)

    @patch('observation_portal.common.state_changes.logger')
    def test_request_debit_on_completion_after_expired_not_enough_time(self, mock_logger):
        request_group = self._build_request_group(self.generic_payload.copy())
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        debitted_ipp_value = time_allocation.ipp_time_available
        self.assertLess(debitted_ipp_value, 5.0)
        # now change requests state to expired
        request = request_group.requests.first()
        request.state = 'WINDOW_EXPIRED'
        request.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        # set the time allocation available to 0.01, then set to completed
        time_allocation.ipp_time_available = 0.01
        time_allocation.save()
        # now set request to completed and see that ipp debitted to 0
        request.state = 'COMPLETED'
        request.save()
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, 0)
        # test that the log message was generated
        self.assertIn('Time available after debiting will be capped at 0',
                      mock_logger.warning.call_args[0][0])

    def test_request_credit_back_on_cancelation(self):
        request_group = self._build_request_group(self.generic_payload.copy())
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertLess(time_allocation.ipp_time_available, 5.0)
        # now change requests state to canceled
        request = request_group.requests.first()
        request.state = 'CANCELED'
        request.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)

    def test_request_credit_on_completion(self):
        payload = self.generic_payload.copy()
        payload['ipp_value'] = 0.5
        request_group = self._build_request_group(payload)
        # verify that now that the TimeAllocation has been debited
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertEqual(time_allocation.ipp_time_available, 5.0)
        # now change requests state to canceled
        request = request_group.requests.first()
        request.state = 'COMPLETED'
        request.save()
        # verify that now that the TimeAllocation has its original ipp value
        time_allocation = TimeAllocation.objects.get(pk=self.time_allocation_1m0.id)
        self.assertGreater(time_allocation.ipp_time_available, 5.0)


class TestWindowApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        mixer.blend(Membership, user=self.user, proposal=self.proposal)

        self.semester = mixer.blend(
            Semester,
            id='2016B',
            start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc),
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            telescope_class='1m0', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id

    def test_post_requestgroup_window_end_before_start(self):
        bad_data = self.generic_payload.copy()
        end = bad_data['requests'][0]['windows'][0]['end']
        start = bad_data['requests'][0]['windows'][0]['start']
        bad_data['requests'][0]['windows'][0]['end'] = start
        bad_data['requests'][0]['windows'][0]['start'] = end

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot be earlier than window start', str(response.content))

    def test_post_requestgroup_no_windows_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['windows'] = []
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['windows']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_window_does_not_fit_in_any_semester(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['windows'][0]['start'] = '2015-01-01 00:00:00'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The observation window does not fit within any defined semester', str(response.content))

    @patch('observation_portal.requestgroups.duration_utils.get_semesters')
    def test_request_windows_are_in_different_semesters(self, mock_get_semesters):
        # Patch get_semesters so that we can add on a window that is in a different valid semester, and still ensure
        # that the semesters that are returned are predictable in this test - the semesters variable used in
        # get_semesters in duration_utils is a global, so it can cause unpredictable results across tests
        another_semester = mixer.blend(
            Semester,
            id='2017A',
            start=datetime(2017, 1, 1, tzinfo=timezone.utc),
            end=datetime(2017, 6, 30, tzinfo=timezone.utc),
        )
        mock_get_semesters.return_value = [self.semester, another_semester]
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['windows'].append({'start': '2017-02-01 00:00:00', 'end': '2017-02-02 00:00:00'})
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The observation windows must all be in the same semester', str(response.content))


class TestCadenceApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()

        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester,
            telescope_class='1m0', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0, instrument_type='1M0-SCICAM-SBIG'
        )

        self.client.force_login(self.user)

        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        del self.generic_payload['requests'][0]['windows']
        self.generic_payload['requests'][0]['cadence'] = {
            'start': '2016-09-01T21:12:18Z',
            'end': '2016-09-03T22:12:19Z',
            'period': 24.0,
            'jitter': 12.0
        }

    def test_post_requestgroup_cadence_and_windows_is_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['windows'] = [{'start': '2016-09-29T21:12:18Z', 'end': '2016-10-29T21:12:19Z'}]
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()['requests'][0]['cadence'])

    def test_post_requestgroup_cadence_is_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['windows'] = []
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        del bad_data['windows']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_cadence_end_before_start_invalid(self):
        bad_data = self.generic_payload.copy()
        end = bad_data['requests'][0]['cadence']['end']
        bad_data['requests'][0]['cadence']['end'] = bad_data['requests'][0]['cadence']['start']
        bad_data['requests'][0]['cadence']['start'] = end
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot be earlier than cadence start', str(response.content))

    def test_post_cadence_end_in_the_past_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['cadence']['end'] = datetime(1901, 1, 1)
        bad_data['requests'][0]['cadence']['start'] = datetime(1900, 1, 1)
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('End time must be in the future', str(response.content))

    def test_post_cadence_valid(self):
        response = self.client.post(reverse('api:request_groups-cadence'), data=self.generic_payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['requests']), 2)

    def test_cadence_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['cadence']['jitter'] = 'bug'
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['cadence']['jitter'], ['A valid number is required.'])

    def test_cadence_with_windows_invalid(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['windows'] = [{'start': '2016-09-29T21:12:18Z', 'end': '2016-10-29T21:12:19Z'}]
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertIn('requests may not contain windows', str(response.content))

    def test_cadence_invalid_period(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['cadence']['period'] = -666
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['cadence']['period'], ['Ensure this value is greater than or equal to 0.02.'])

    def test_post_requestgroup_after_valid_cadence(self):
        response = self.client.post(reverse('api:request_groups-cadence'), data=self.generic_payload)
        second_response = self.client.post(reverse('api:request_groups-list'), data=response.json())
        self.assertEqual(second_response.status_code, 201)
        self.assertGreater(self.user.requestgroup_set.all().count(), 0)

    def test_post_cadence_with_invalid_request(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'].append('invalid_request')
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid data. Expected a dictionary, but got str.', str(response.content))

    def test_post_cadence_with_no_visible_requests(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['cadence']['end'] = '2016-09-01T21:13:18Z'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_count'] = 100
        bad_data['requests'][0]['cadence']['jitter'] = 0.02
        bad_data['requests'][0]['cadence']['period'] = 0.02
        response = self.client.post(reverse('api:request_groups-cadence'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('No visible requests within cadence window parameters', str(response.content))


class TestICRSTarget(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
                               end=datetime(2016, 12, 31, tzinfo=timezone.utc)
                               )
        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0,
            std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )

        self.time_allocation_2m0_floyds = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester,
            instrument_type='2M0-FLOYDS-SCICAM', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )

        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id

    def test_post_requestgroup_no_ra(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['target']['ra']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('ra', str(response.content))

    def test_post_requestgroup_extra_ns_field(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['longascnode'] = 4.0
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 201)
        target = response.json()['requests'][0]['configurations'][0]['target']
        self.assertNotIn('longascnode', target)

    def test_post_requestgroup_test_defaults(self):
        bad_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 201)
        target = response.json()['requests'][0]['configurations'][0]['target']
        self.assertEqual(target['proper_motion_ra'], 0.0)
        self.assertEqual(target['proper_motion_dec'], 0.0)
        self.assertEqual(target['parallax'], 0.0)
        self.assertEqual(target['epoch'], 2000.0)

    def test_post_requestgroup_test_proper_motion_no_epoch(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['proper_motion_ra'] = 1.0
        bad_data['requests'][0]['configurations'][0]['target']['proper_motion_dec'] = 1.0
        # epoch defaults to 2000 so we should pass
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_test_proper_motion_with_epoch(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['proper_motion_ra'] = 1.0
        bad_data['requests'][0]['configurations'][0]['target']['proper_motion_dec'] = 1.0
        bad_data['requests'][0]['configurations'][0]['target']['epoch'] = 2001.0
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 201)

    def test_floyds_gets_vfloat_default(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data, follow=True)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rotator_mode'], 'VFLOAT')

    def test_target_name_max_length(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['name'] = 'x' * 51
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data, follow=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn('50 characters', str(response.content))


class TestOrbitalElementsTarget(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)
        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            instrument_type='1M0-SCICAM-SBIG', rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['requests'][0]['configurations'][0]['target'] = {
            'name': 'fake target',
            'type': 'ORBITAL_ELEMENTS',
            'scheme': 'MPC_MINOR_PLANET',
            # Non sidereal param
            'epochofel': 57660.0,
            'orbinc': 9.7942900,
            'longascnode': 122.8943400,
            'argofperih': 78.3278300,
            'perihdist': 1.0,
            'meandist': 0.7701170,
            'meananom': 165.6860400,
            'eccentricity': 0.5391962,
            'epochofperih': 57400.0,
        }

    def test_post_requestgroup_invalid_target_type(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['type'] = 'NOTATYPE'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_orbital_elements_target(self):
        good_data = self.generic_payload.copy()

        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_bad_comet_eccentricity(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['eccentricity'] = 0.99

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('requires eccentricity to be lower', str(response.content))

    def test_post_requestgroup_orbital_elements_mpc_comet(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['target']['eccentricity'] = 0.99
        good_data['requests'][0]['configurations'][0]['target']['scheme'] = 'MPC_COMET'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_orbital_elements_target_not_visible(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['eccentricity'] = 0.99
        bad_data['requests'][0]['configurations'][0]['target']['scheme'] = 'MPC_COMET'
        bad_data['requests'][0]['configurations'][0]['target']['perihdist'] = 5.0

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('the target is never visible within the time window', str(response.content))

    def test_post_requestgroup_orbital_elements_target_missing_fields(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['target']['eccentricity']
        del bad_data['requests'][0]['configurations'][0]['target']['meandist']

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('eccentricity', str(response.content))
        self.assertIn('meandist', str(response.content))

    def test_post_requestgroup_jpl_major_planet(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['target'] = {
            "name": "Saturn",
            "type": "ORBITAL_ELEMENTS",
            "scheme": "JPL_MAJOR_PLANET",
            "orbinc": "2.490066187978994",
            "longascnode": "113.5557964913403",
            "argofperih": "340.0784134626224",
            "eccentricity": "0.05143457699730554",
            "meandist": "9.573276502591009",
            "meananom": "174.0162055524961",
            "epochofel": "58052",
            "dailymot": "0.03327937986031185"
        }
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_invalid_ephemeris(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['target']['meandist'] = 0.00000000000001
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)


class TestSatelliteTarget(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            instrument_type='1M0-SCICAM-SBIG', rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['requests'][0]['configurations'][0]['target'] = {
            'name': 'fake target',
            'type': 'SATELLITE',
            # satellite
            'altitude': 33.0,
            'azimuth': 2.0,
            'diff_altitude_rate': 3.0,
            'diff_azimuth_rate': 4.0,
            'diff_altitude_acceleration': 5.0,
            'diff_azimuth_acceleration': 0.99,
            'diff_epoch': 22.0,
            'epoch': 2000.0,
        }

    def test_post_requestgroup_satellite_target(self):
        good_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_satellite_missing_fields(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['target']['diff_epoch']
        del bad_data['requests'][0]['configurations'][0]['target']['diff_altitude_acceleration']

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('diff_epoch', str(response.content))
        self.assertIn('diff_altitude_acceleration', str(response.content))


class TestHourAngleTarget(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            instrument_type='1M0-SCICAM-SBIG', rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['requests'][0]['configurations'][0]['target'] = {
            'name': 'fake target',
            'type': 'HOUR_ANGLE',
            'hour_angle': 20.0,
            'dec': 30.0,
            'parallax': 0.1,
            'proper_motion_ra': 0.01,
            'proper_motion_dec': 0.02,
            'epoch': 2000
        }

    def test_post_requestgroup_hour_angle_target_fails(self):
        bad_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('HOUR_ANGLE Target type not supported', str(response.content))


class TestLocationApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0,
            instrument_type='1M0-SCICAM-SBIG'
        )
        self.time_allocation_2m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0,
            instrument_type='2M0-FLOYDS-SCICAM'
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id

    def test_post_requestgroup_all_location_info(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['site'] = 'tst'
        good_data['requests'][0]['location']['enclosure'] = 'doma'
        good_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_post_requestgroup_observatory_no_site(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['enclosure'] = 'doma'
        good_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_observatory_no_observatory(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['site'] = 'tst'
        good_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_observatory_bad_observatory(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = 'tst'
        bad_data['requests'][0]['location']['enclosure'] = 'domx'
        bad_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_observatory_bad_site(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = 'bpl'
        bad_data['requests'][0]['location']['enclosure'] = 'doma'
        bad_data['requests'][0]['location']['telescope'] = '1m0a'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_observatory_bad_telescope(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = 'tst'
        bad_data['requests'][0]['location']['enclosure'] = 'doma'
        bad_data['requests'][0]['location']['telescope'] = '1m0b'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

    def test_post_requestgroup_location_no_blanks(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['site'] = 'tst'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()['requests'][0]['location'].get('observatory'))

    def test_post_requestgroup_location_instrument_doesnt_match_class(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-SCICAM-SBIG'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertNotEqual(response.status_code, 201)


class TestConfigurationApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='1M0-SCICAM-SBIG',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.time_allocation_1m0_nres = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='1M0-NRES-SCICAM',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.time_allocation_2m0_floyds = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='2M0-FLOYDS-SCICAM',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.time_allocation_soar = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='1M0-SCICAM-SOAR',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.extra_configuration = copy.deepcopy(self.generic_payload['requests'][0]['configurations'][0])

    def test_must_have_at_least_one_instrument_config(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'] = []
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('must have at least one instrument configuration', str(response.content))

    def test_extra_params_saved_as_float_not_string(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['extra_params'] = {'test_value': '1.15'}
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        extra_params = response.json()['requests'][0]['configurations'][0]['extra_params']
        self.assertEqual(extra_params['test_value'], 1.15)

    def test_extra_param_set_to_none_ok(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['extra_params'] = {'test_value': None}
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['extra_params']['test_value'], None)

    def test_extra_param_set_to_string_ok(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['extra_params'] = {'test_value': ''}
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['extra_params']['test_value'], '')

    def test_must_have_exposure_time(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time', str(response.content))

    def test_must_have_positive_exposure_time(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = -10.1
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time', str(response.content))

    def test_must_have_non_nan_exposure_time(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = 'nan'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time', str(response.content))

    def test_bad_defocus_values_must_not_be_submitted(self):
        bad_data = self.generic_payload.copy()
        bad_values = ['2mm', '']
        for bad_value in bad_values:
            with self.subTest(bad_value=bad_value):
                bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params'] = {
                    'defocus': bad_value
                }
                response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
                self.assertEqual(response.status_code, 400)
                self.assertIn('Defocus', str(response.content))

    def test_defocus_as_a_number_successfully_submits(self):
        good_data = self.generic_payload.copy()
        good_values = [2, '2']
        expected_submitted_defocus = 2
        for good_value in good_values:
            with self.subTest(good_value=good_value):
                good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params'] = {
                    'defocus': good_value
                }
                r = self.client.post(reverse('api:request_groups-list'), data=good_data)
                self.assertEqual(r.status_code, 201)
                self.assertEqual(
                    r.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['defocus'],
                    expected_submitted_defocus
                )

    def test_default_guide_mode_for_spectrograph(self):
        good_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        configuration = response.json()['requests'][0]['configurations'][0]
        # check that without spectral instrument, these defaults are different
        self.assertTrue(configuration['guiding_config']['optional'])
        self.assertEqual(configuration['guiding_config']['mode'], 'OFF')
        self.assertNotIn('slit', configuration['instrument_configs'][0]['optical_elements'])

        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        configuration = response.json()['requests'][0]['configurations'][0]
        # now with spectral instrument, defaults have changed
        self.assertEqual(configuration['guiding_config']['mode'], 'ON')
        self.assertFalse(configuration['guiding_config']['optional'])
        self.assertEqual(configuration['instrument_configs'][0]['optical_elements']['slit'], 'slit_6.0as')

    def test_guide_mode_off_not_allowed_for_nres_spectrum(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'NRES_SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'OFF'

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Guiding mode OFF is not available for instrument type', str(response.content))

    def test_guide_optional_not_allowed_for_spectrum(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['telescope_class'] = '2m0'
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['guiding_config']['optional'] = True

        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Guiding cannot be optional on spectrograph instruments', str(response.content))

    def test_guide_optional_allowed_for_arc(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        good_data['requests'][0]['configurations'][0]['type'] = 'ARC'
        good_data['requests'][0]['configurations'][0]['guiding_config']['optional'] = True
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_1.6as'

        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_guiding_mode_not_available(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'I_DONT_EXIST'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Guiding mode I_DONT_EXIST is not available', str(response.content))

    def test_readout_mode_many_options(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'NRES_SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements'] = {}
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['mode'] = ''
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x']
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Must set a readout mode, choose from', str(response.content))

    def test_instrument_type_does_not_have_readout_mode_then_mode_stays_blank(self):
        good_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rotator_mode'], '')

    def test_readout_mode_not_set_and_no_default_but_single_option_set(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['mode']
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_1.6as'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        # The only readout mode for floyds is 2m0_floyds_1
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['mode'], '2m0_floyds_1')

    def test_repeat_exposure_rejected_without_configuration_duration_set(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Must specify a configuration repeat_duration for REPEAT_EXPOSE type configurations.',
                      str(response.content))

    def test_repeat_duration_rejected_for_non_repeat_exposure(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['repeat_duration'] = 500.0
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('You may only specify a repeat_duration for REPEAT_* type configurations.',
                      str(response.content))

    def test_repeat_exposure_accepted_when_configuration_duration_fits_instrument_configs(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        good_data['requests'][0]['configurations'][0]['repeat_duration'] = 500.0
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_repeat_exposure_rejected_when_configuration_duration_too_small(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        bad_data['requests'][0]['configurations'][0]['repeat_duration'] = 1.0
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Configuration repeat_duration of 1.0 is less than the minimum',
                      str(response.content))

    def test_many_missing_required_fields(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        bad_data['requests'][0]['configurations'][0]['type'] = 'NRES_SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements'] = {}
        bad_data['requests'][0]['configurations'][0]['acquisition_config']['mode'] = 'MYMODE'
        bad_data['requests'][0]['configurations'][0]['acquisition_config']['extra_params']['field1'] = 'some-arg'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Acquisition mode MYMODE requirements are not met: extra_params{field2 error: required field, field3 error: required field}', str(response.content))

    def test_invalid_filter_for_instrument(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter'] = 'magic'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('optical element magic of type filter is not available', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_filter_case_is_overridden(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter'] = 'AiR'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter'], 'air')
        self.assertEqual(response.status_code, 201)

    def test_filter_not_necessary_for_type(self):
        good_data = self.generic_payload.copy()

        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['type'] = 'ARC'
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_6.0as'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_script_name_required_for_script_type(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'SCRIPT'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Must specify a script_name', str(response.content))
        self.assertEqual(response.status_code, 400)

        good_data = bad_data
        good_data['requests'][0]['configurations'][0]['extra_params'] = {'script_name': 'auto_focus'}
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_zero_length_exposure_allowed(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = 0
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_slit_not_necessary_for_nres(self):
        good_data = self.generic_payload.copy()
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        good_data['requests'][0]['configurations'][0]['type'] = 'NRES_SPECTRUM'
        good_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'ON'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        good_data['requests'][0]['configurations'][0]['type'] = 'NRES_EXPOSE'
        good_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'ON'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        good_data['requests'][0]['configurations'][0]['type'] = 'NRES_TEST'
        good_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'ON'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_nres_parameters_passthrough(self):
        good_data = self.generic_payload.copy()
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-NRES-SCICAM'
        good_data['requests'][0]['configurations'][0]['type'] = 'NRES_SPECTRUM'
        good_data['requests'][0]['configurations'][0]['guiding_config']['mode'] = 'ON'
        good_data['requests'][0]['configurations'][0]['acquisition_config']['mode'] = 'WCS'
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params'] = {
            'expmeter_snr': 10.0,
            'expmeter_mode': 'OFF'
        }
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        configuration = response.json()['requests'][0]['configurations'][0]
        self.assertEqual(configuration['instrument_configs'][0]['extra_params']['expmeter_snr'], 10.0)
        self.assertEqual(configuration['instrument_configs'][0]['extra_params']['expmeter_mode'], 'OFF')
        self.assertEqual(configuration['acquisition_config']['mode'], 'WCS')
        self.assertEqual(configuration['guiding_config']['mode'], 'ON')

    def test_filter_necessary_for_type(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Must set optical element of type filter', str(response.content))

    def test_invalid_spectra_slit_for_instrument(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        bad_data['requests'][0]['location']['telescope_class'] = '2m0'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_really_small'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('optical element slit_really_small of type slit is not available', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_invalid_binning_for_instrument(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x'] = 5
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y'] = 5
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('No readout mode found with binning 5', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_invalid_binning_for_instrument_for_mode(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['mode'] = '1m0_sbig_2'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x'] = 5
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y'] = 5
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Readout mode 1m0_sbig_2 requirements are not met: bin_x error: unallowed value 5, bin_y error: unallowed value 5', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_readout_mode_sets_default_binning(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['mode'] = '1m0_sbig_2'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x']
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 201)
        rg = response.json()
        self.assertEqual(rg['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x'], 2)
        self.assertEqual(rg['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y'], 2)

    def test_default_binning_for_instrument(self):
        good_data = self.generic_payload.copy()
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x']
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y']
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        configuration = response.json()['requests'][0]['configurations'][0]
        self.assertEqual(configuration['instrument_configs'][0]['bin_x'], 2)
        self.assertEqual(configuration['instrument_configs'][0]['bin_y'], 2)

    def test_different_x_and_y_binnings_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x'] = 1
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y'] = 2
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Currently only square binnings are supported. Please submit with bin_x == bin_y', str(response.content))

    def test_binx_set_if_only_biny_is_input(self):
        data = self.generic_payload.copy()
        del data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_x']
        response = self.client.post(reverse('api:request_groups-list'), data=data)
        self.assertEqual(response.status_code, 201)
        instrument_configuration = response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]
        self.assertEqual(instrument_configuration['bin_x'], instrument_configuration['bin_y'])

    def test_biny_set_if_only_binx_is_input(self):
        data = self.generic_payload.copy()
        del data['requests'][0]['configurations'][0]['instrument_configs'][0]['bin_y']
        response = self.client.post(reverse('api:request_groups-list'), data=data)
        self.assertEqual(response.status_code, 201)
        instrument_configuration = response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]
        self.assertEqual(instrument_configuration['bin_x'], instrument_configuration['bin_y'])

    def test_request_invalid_instrument_type(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = 'FAKE-INSTRUMENT'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Invalid instrument type', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_request_invalid_instrument_type_for_location(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['location']['site'] = "lco"
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn("Invalid instrument type \\\'1M0-SCICAM-SBIG\\\' at site", str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_configurations_automatically_have_priority_set(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'].append(copy.deepcopy(self.extra_configuration))
        good_data['requests'][0]['configurations'].append(copy.deepcopy(self.extra_configuration))
        good_data['requests'][0]['configurations'].append(copy.deepcopy(self.extra_configuration))
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        rg = response.json()
        self.assertEqual(response.status_code, 201)
        for i, configuration in enumerate(rg['requests'][0]['configurations']):
            self.assertEqual(configuration['priority'], i + 1)

    def test_fill_window_on_more_than_one_configuration_fails(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        bad_data['requests'][0]['configurations'][0]['repeat_duration'] = 250
        bad_data['requests'][0]['configurations'].append(
            bad_data['requests'][0]['configurations'][0].copy()
        )
        bad_data['requests'][0]['configurations'][0]['fill_window'] = True
        bad_data['requests'][0]['configurations'][1]['fill_window'] = True
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Only one configuration can have `fill_window` set', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_fill_window_one_configuration_fills_the_window(self):
        good_data = self.generic_payload.copy()
        initial_repeat_duration = 250
        good_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        good_data['requests'][0]['configurations'][0]['repeat_duration'] = initial_repeat_duration
        good_data['requests'][0]['configurations'][0]['fill_window'] = True
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        rg = response.json()
        self.assertGreater(rg['requests'][0]['configurations'][0]['repeat_duration'],
                           initial_repeat_duration)
        self.assertEqual(response.status_code, 201)

    def test_fill_window_two_configs_one_false_fills_the_window(self):
        good_data = self.generic_payload.copy()
        initial_repeat_duration = 250
        good_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        good_data['requests'][0]['configurations'][0]['repeat_duration'] = initial_repeat_duration
        good_data['requests'][0]['configurations'].append(
            good_data['requests'][0]['configurations'][0].copy()
        )
        good_data['requests'][0]['configurations'][0]['fill_window'] = True
        good_data['requests'][0]['configurations'][1]['fill_window'] = False
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        rg = response.json()
        self.assertGreater(rg['requests'][0]['configurations'][0]['repeat_duration'],
                           initial_repeat_duration)
        self.assertEqual(rg['requests'][0]['configurations'][1]['repeat_duration'],
                         initial_repeat_duration)
        self.assertEqual(response.status_code, 201)

    def test_fill_window_two_configs_one_blank_fills_the_window(self):
        good_data = self.generic_payload.copy()
        initial_repeat_duration = 250
        good_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        good_data['requests'][0]['configurations'][0]['repeat_duration'] = initial_repeat_duration
        good_data['requests'][0]['configurations'].append(
            good_data['requests'][0]['configurations'][0].copy()
        )
        good_data['requests'][0]['configurations'][0]['fill_window'] = True
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        rg = response.json()
        self.assertGreater(rg['requests'][0]['configurations'][0]['repeat_duration'],
                           initial_repeat_duration)
        self.assertEqual(rg['requests'][0]['configurations'][1]['repeat_duration'],
                         initial_repeat_duration)
        self.assertEqual(response.status_code, 201)

    def test_fill_window_not_enough_time_fails(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['windows'][0] = {
            'start': '2016-09-29T21:12:18Z',
            'end': '2016-09-29T21:21:19Z'
        }
        bad_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        bad_data['requests'][0]['configurations'][0]['repeat_duration'] = 250
        bad_data['requests'][0]['configurations'][0]['fill_window'] = True
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('the target is never visible within the time window', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_fill_window_confined_window_fills_the_window(self):
        good_data = self.generic_payload.copy()
        initial_repeat_duration = 250
        good_data['requests'][0]['windows'][0] = {
            'start': '2016-09-29T23:12:18Z',
            'end': '2016-09-29T23:21:19Z'
        }
        good_data['requests'][0]['configurations'][0]['type'] = 'REPEAT_EXPOSE'
        good_data['requests'][0]['configurations'][0]['repeat_duration'] = initial_repeat_duration
        good_data['requests'][0]['configurations'][0]['fill_window'] = True
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        rg = response.json()
        self.assertGreater(rg['requests'][0]['configurations'][0]['repeat_duration'],
                           initial_repeat_duration)
        self.assertEqual(rg['requests'][0]['configurations'][0]['repeat_duration'], 430.0)
        self.assertEqual(response.status_code, 201)

    def test_multiple_instrument_configs_with_different_rotator_modes_fails(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'].append(
            self.extra_configuration['instrument_configs'][0].copy()
        )
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        bad_data['requests'][0]['location']['telescope_class'] = '2m0'
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][1]['optical_elements']['filter']
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_1.6as'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][1]['optical_elements']['slit'] = 'slit_1.6as'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rotator_mode'] = 'SKY'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params'] = {}
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['rotator_angle'] = '1'
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][1]['rotator_mode'] = 'VFLOAT'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('within the same configuration must be the same', str(response.content))

    def test_multiple_instrument_configs_with_same_rotator_modes_succeeds(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'].append(
            self.extra_configuration['instrument_configs'][0].copy()
        )
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        good_data['requests'][0]['location']['telescope_class'] = '2m0'
        good_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][1]['optical_elements']['filter']
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_1.6as'
        good_data['requests'][0]['configurations'][0]['instrument_configs'][1]['optical_elements']['slit'] = 'slit_1.6as'
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rotator_mode'] = 'VFLOAT'
        good_data['requests'][0]['configurations'][0]['instrument_configs'][1]['rotator_mode'] = 'VFLOAT'
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_script_type_not_allowed_for_multiple_instrument_configs(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'].append(
            self.extra_configuration['instrument_configs'][0].copy()
        )
        bad_data['requests'][0]['configurations'][0]['type'] = 'SCRIPT'
        bad_data['requests'][0]['configurations'][0]['extra_params'] = {}
        bad_data['requests'][0]['configurations'][0]['extra_params']['script_name'] = 'my_cool_thing'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('are not allowed for type SCRIPT', str(response.content))

    def test_skyflat_not_allowed_for_multiple_instrument_configs(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'].append(
            self.extra_configuration['instrument_configs'][0].copy()
        )
        bad_data['requests'][0]['configurations'][0]['type'] = 'SKY_FLAT'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('are not allowed for type SKY_FLAT', str(response.content))

    def test_configuration_type_matches_instrument(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['type'] = 'SPECTRUM'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('configuration type SPECTRUM is not valid for instrument type 1M0-SCICAM-SBIG', str(response.content))
        self.assertEqual(response.status_code, 400)

        bad_data['requests'][0]['configurations'][0]['type'] = 'EXPOSE'
        bad_data['requests'][0]['configurations'][0]['instrument_type'] = '2M0-FLOYDS-SCICAM'
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit'] = 'slit_1.6as'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('configuration type EXPOSE is not valid for instrument type 2M0-FLOYDS-SCICAM', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_acquisition_config_exposure_time_limits(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['acquisition_config']['exposure_time'] = -1
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['acquisition_config']['exposure_time'] = 65
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)

        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['acquisition_config']['exposure_time'] = 20
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        ur = response.json()
        self.assertEqual(ur['requests'][0]['configurations'][0]['acquisition_config']['exposure_time'], 20)
        self.assertEqual(response.status_code, 201)

    def test_acquisition_config_no_exposure_time_works(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['acquisition_config']['exposure_time'] = None
        response = self.client.post(reverse('api:request_groups-validate'), data=good_data)
        self.assertEqual(response.status_code, 200)

    def test_more_than_max_rois_rejected(self):
        roi_data = {'x1': 0, 'x2': 20, 'y1': 0, 'y2': 100}
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [roi_data, roi_data]
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertIn('Instrument type 1M0-SCICAM-SBIG supports up to 1 regions of interest', str(response.content))
        self.assertEqual(response.status_code, 400)

    def test_rois_outside_ccd_area_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'x2': 2000}]
        response1 = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'y2': 3000}]
        response2 = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        for response in [response1, response2]:
            self.assertIn('Regions of interest for instrument type 1M0-SCICAM-SBIG must be in range', str(response.content))
            self.assertEqual(response.status_code, 400)

    def test_rois_start_pixels_larger_than_end_pixels_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'x1': 1000, 'x2': 400}]
        response1 = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'y1': 500, 'y2': 300}]
        response2 = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        for response in [response1, response2]:
            self.assertIn('Region of interest pixels start must be less than pixels end', str(response.content))
            self.assertEqual(response.status_code, 400)

    def test_valid_rois_accepted(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'x1': 0, 'x2': 20, 'y1': 0, 'y2': 100}]
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rois']), 1)

    def test_sparse_roi_fields_sets_defaults(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{'x1': 100}]
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rois']), 1)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'][0]['x2'], 1000)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'][0]['y2'], 1000)
        self.assertEqual(response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'][0]['y1'], 0)

    def test_empty_roi_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['rois'] = [{}]
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Must submit at least one bound for a region of interest', str(response.content))

    def test_multiple_same_targets_and_constraints_accepted(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'].append(
            copy.deepcopy(good_data['requests'][0]['configurations'][0])
        )
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_multiple_targets_currently_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'].append(
            copy.deepcopy(bad_data['requests'][0]['configurations'][0])
        )
        bad_data['requests'][0]['configurations'][1]['target']['ra'] = 35.1
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Currently only a single target', str(response.content))

    def test_multiple_targets_soar_accepted(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-SCICAM-SOAR'
        good_data['requests'][0]['configurations'].append(
            copy.deepcopy(good_data['requests'][0]['configurations'][0])
        )
        good_data['requests'][0]['configurations'][1]['target']['ra'] = 35.1
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

    def test_multiple_constraints_currently_rejected(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'].append(
            copy.deepcopy(bad_data['requests'][0]['configurations'][0])
        )
        bad_data['requests'][0]['configurations'][1]['constraints']['max_airmass'] = 1.99
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Currently only a single constraints', str(response.content))

    def test_multiple_constraints_soar_accepted(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_type'] = '1M0-SCICAM-SOAR'
        good_data['requests'][0]['configurations'].append(
            copy.deepcopy(good_data['requests'][0]['configurations'][0])
        )
        good_data['requests'][0]['configurations'][1]['constraints']['max_airmass'] = 1.99
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)

class TestMuscatValidationApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user()
        self.client.force_login(self.user)

        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, instrument_type='2M0-SCICAM-MUSCAT',
            std_allocation=100.0, std_time_used=0.0, rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.generic_payload['requests'][0]['configurations'][0]['instrument_type'] = '2M0-SCICAM-MUSCAT'
        self.generic_payload['requests'][0]['location']['telescope_class'] = '2m0'
        del self.generic_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['filter']
        self.generic_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params'] = {
            'exposure_time_g': 33.0,
            'exposure_time_r': 29.0,
            'exposure_time_i': 27.5,
            'exposure_time_z': 25.8,
            'exposure_mode': 'SYNCHRONOUS'
        }
        self.generic_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements'] = {
            'diffuser_g_position': "in",
            'diffuser_r_position': "out",
            'diffuser_i_position': "out",
            'diffuser_z_position': "out",
        }

    def test_accepts_good_muscat_request(self):
        good_data = self.generic_payload.copy()
        max_exposure_time = good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_time_g']
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        inst_config = response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]
        # check that the exposure_time field was set to the max of the extra params exposure times
        self.assertEqual(inst_config['exposure_time'], max_exposure_time)

    def test_sets_default_muscat_exposure_mode(self):
        good_data = self.generic_payload.copy()
        del good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_mode']
        response = self.client.post(reverse('api:request_groups-list'), data=good_data)
        self.assertEqual(response.status_code, 201)
        inst_config = response.json()['requests'][0]['configurations'][0]['instrument_configs'][0]
        # check that the exposure_mode field is set to the default of SYNCHRONOUS
        self.assertEqual(inst_config['extra_params']['exposure_mode'], 'SYNCHRONOUS')

    def test_muscat_requires_extra_params_exposure_times_set(self):
        bad_data = self.generic_payload.copy()
        del bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_time_g']
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time_g', str(response.content))

    def test_muscat_rejects_bad_exposure_mode(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_mode'] = "Invalid"
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Exposure mode Invalid', str(response.content))

    def test_muscat_extra_param_exposure_time_must_be_number(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_time_g'] = 'NotANumber'
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time_g error: must be of float type', str(response.content))

    def test_muscat_extra_param_exposure_time_must_be_positive(self):
        bad_data = self.generic_payload.copy()
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_time_g'] = -33.2
        bad_data['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['exposure_time_i'] = -33.2
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('exposure_time_g error: min value is 0', str(response.content))
        self.assertIn('exposure_time_i error: min value is 0', str(response.content))

    def test_do_not_allow_more_than_one_instrument_config(self):
        bad_data = self.generic_payload.copy()
        instrument_config = copy.deepcopy(bad_data['requests'][0]['configurations'][0]['instrument_configs'][0])
        bad_data['requests'][0]['configurations'][0]['instrument_configs'].append(instrument_config)
        response = self.client.post(reverse('api:request_groups-list'), data=bad_data)
        expected_message = 'Multiple instrument configs are not allowed for the instrument 2M0-SCICAM-MUSCAT'
        self.assertContains(response, expected_message, status_code=400)


class TestGetRequestApi(APITestCase):
    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal)
        self.user = blend_user(user_params={'is_staff': False, 'is_superuser': False})
        self.staff_user = blend_user(user_params={'is_staff': True})
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.request_group = mixer.blend(RequestGroup, submitter=self.user, proposal=self.proposal,
                                         observation_type=RequestGroup.NORMAL)

    def test_get_request_list_authenticated(self):
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote')
        mixer.blend(Location, request=request)
        mixer.blend(Window, request=request)
        config = mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        mixer.blend(Constraints, configuration=config)
        mixer.blend(InstrumentConfig, configuration=config)
        mixer.blend(AcquisitionConfig, configuration=config)
        mixer.blend(GuidingConfig, configuration=config)
        self.client.force_login(self.user)
        result = self.client.get(reverse('api:requests-list'))
        self.assertEqual(result.json()['results'][0]['observation_note'], request.observation_note)

    def test_get_request_list_unauthenticated(self):
        mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote')
        result = self.client.get(reverse('api:requests-list'))
        self.assertNotContains(result, 'testobsnote')
        self.assertEqual(result.status_code, 200)

    def test_get_request_detail_authenticated(self):
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote')
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.user)
        result = self.client.get(reverse('api:requests-detail', args=(request.id,)))
        self.assertEqual(result.json()['observation_note'], request.observation_note)

    def test_get_request_detail_unauthenticated(self):
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote')
        result = self.client.get(reverse('api:requests-detail', args=(request.id,)))
        self.assertEqual(result.status_code, 404)

    def test_get_request_detail_staff_no_staff_view(self):
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote2')
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:requests-detail', args=(request.id,)))
        self.assertEqual(result.status_code, 404)

    def test_get_request_detail_staff_with_staff_view(self):
        self.staff_user.profile.staff_view = True
        self.staff_user.profile.save()
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote2')
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:requests-detail', args=(request.id,)))
        self.assertEqual(result.json()['observation_note'], request.observation_note)

    def test_request_detail_with_view_authored_requests_only(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        self.client.force_login(self.user)
        non_authored_request_group = mixer.blend(
            RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.staff_user,
            observation_type=RequestGroup.NORMAL
        )
        non_authored_request = mixer.blend(Request, request_group=non_authored_request_group)
        mixer.blend(Configuration, request=non_authored_request, instrument_type='1M0-SCICAM-SBIG')
        authored_request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote')
        mixer.blend(Configuration, request=authored_request, instrument_type='1M0-SCICAM-SBIG')
        response = self.client.get(reverse('api:requests-detail', args=(non_authored_request.id,)))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('api:requests-detail', args=(authored_request.id,)))
        self.assertContains(response, authored_request.id)

    def test_get_request_list_staff_no_staff_view(self):
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote2')
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:requests-list'))
        self.assertEqual(len(result.json()['results']), 0)

    def test_get_request_list_staff_with_staff_view(self):
        self.staff_user.profile.staff_view = True
        self.staff_user.profile.save()
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote2')
        create_simple_configuration(request=request)
        self.client.force_login(self.staff_user)
        result = self.client.get(reverse('api:requests-list'))
        self.assertEqual(result.json()['results'][0]['observation_note'], request.observation_note)

    def test_get_request_detail_public(self):
        proposal = mixer.blend(Proposal, public=True)
        self.request_group.proposal = proposal
        self.request_group.save()
        request = mixer.blend(Request, request_group=self.request_group, observation_note='testobsnote2')
        mixer.blend(Configuration, request=request, instrument_='1M0-SCICAM-SBIG')
        self.client.logout()
        result = self.client.get(reverse('api:requests-detail', args=(request.id,)))
        self.assertEqual(result.json()['observation_note'], request.observation_note)


class TestDraftRequestGroupApi(APITestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('api:drafts-list'))
        self.assertEqual(response.status_code, 403)

    def test_user_can_list_drafts(self):
        mixer.cycle(5).blend(DraftRequestGroup, author=self.user, proposal=self.proposal)
        response = self.client.get(reverse('api:drafts-list'))
        self.assertContains(response, self.proposal.id)
        self.assertEqual(response.json()['count'], 5)

    def test_user_can_list_proposal_drafts(self):
        other_user = blend_user()
        mixer.blend(Membership, user=other_user, proposal=self.proposal)
        mixer.cycle(5).blend(DraftRequestGroup, author=other_user, proposal=self.proposal)
        response = self.client.get(reverse('api:drafts-list'))
        self.assertContains(response, self.proposal.id)
        self.assertEqual(response.json()['count'], 5)

    def test_user_can_create_draft(self):
        data = {
            'proposal': self.proposal.id,
            'title': 'Test Draft',
            'content': '{"foo": "bar"}'
        }
        response = self.client.post(reverse('api:drafts-list'), data=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['title'], data['title'])

    def test_post_invalid_json(self):
        data = {
            'proposal': self.proposal.id,
            'content': 'foo: bar'
        }
        response = self.client.post(reverse('api:drafts-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Content must be valid JSON', response.json()['content'])

    def test_post_wrong_proposal(self):
        other_proposal = mixer.blend(Proposal)
        data = {
            'proposal': other_proposal.id,
            'title': 'I cant do this',
            'content': '{"foo": "bar"}'
        }
        response = self.client.post(reverse('api:drafts-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('You are not a member of that proposal', response.json()['non_field_errors'])

    def test_user_cannot_duplicate_draft(self):
        mixer.blend(DraftRequestGroup, author=self.user, proposal=self.proposal, title='dup')
        data = {
            'proposal': self.proposal.id,
            'title': 'dup',
            'content': '{"foo": "bar"}'
        }
        response = self.client.post(reverse('api:drafts-list'), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The fields author, proposal, title must make a unique set.', str(response.content))

    def test_user_can_update_draft(self):
        draft = mixer.blend(DraftRequestGroup, author=self.user, proposal=self.proposal)
        data = {
            'proposal': self.proposal.id,
            'title': 'an updated draft',
            'content': '{"updated": true}'
        }
        response = self.client.put(reverse('api:drafts-detail', args=(draft.id,)), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DraftRequestGroup.objects.get(id=draft.id).title, 'an updated draft')

    def test_user_can_delete_draft(self):
        draft = mixer.blend(DraftRequestGroup, author=self.user, proposal=self.proposal)
        response = self.client.delete(reverse('api:drafts-detail', args=(draft.id,)))
        self.assertEqual(response.status_code, 204)

    def test_user_cannot_delete_other_draft(self):
        other_user = blend_user()
        other_proposal = mixer.blend(Proposal)
        draft = mixer.blend(DraftRequestGroup, author=other_user, proposal=other_proposal)
        response = self.client.delete(reverse('api:drafts-detail', args=(draft.id,)))
        self.assertEqual(response.status_code, 404)


class TestAirmassApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        mixer.blend(
            Semester, id='2016B',
            start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.request = {
            'configurations': [{
                'type': 'EXPOSE',
                'instrument_type': '1M0-SCICAM-SBIG',
                'instrument_configs': [
                    {
                        'exposure_time': 100,
                        'exposure_count': 1,
                        'bin_x': 1,
                        'bin_y': 1,
                        'optical_elements': {'filter': 'air'}
                     }
                ],
                'guiding_config': {},
                'acquisition_config': {},
                'constraints': {
                    'max_airmass': 2.0,
                    'min_lunar_distance': 30.0,
                },
                'target': {
                    'name': 'fake target',
                    'type': 'ICRS',
                    'dec': 20,
                    'ra': 34.4,
                }

            }],
            'windows': [{
                'start': '2016-09-29T21:12:18Z',
                'end': '2016-10-29T21:12:19Z'
            }],
            'location': {
                'telescope_class': '1m0',
            },
        }

    def test_airmass(self):
        response = self.client.post(reverse('api:airmass'), data=self.request)
        self.assertIn('tst', response.json()['airmass_data'])
        self.assertTrue(response.json()['airmass_data']['tst']['times'])


@patch('observation_portal.common.state_changes.modify_ipp_time_from_requests')
class TestCancelRequestGroupApi(SetTimeMixin, APITestCase):
    ''' Test canceling user requests via API. Mocking out modify_ipp_time_from_requets
        as it is called on state change, but tested elsewhere '''
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)

    def test_cancel_pending_rg(self, modify_mock):
        requestgroup = mixer.blend(RequestGroup, state='PENDING', proposal=self.proposal,
                                   observation_type=RequestGroup.NORMAL)
        requests = mixer.cycle(3).blend(Request, state='PENDING', request_group=requestgroup)
        for request in requests:
            mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')

        response = self.client.post(reverse('api:request_groups-cancel', kwargs={'pk': requestgroup.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestGroup.objects.get(pk=requestgroup.id).state, 'CANCELED')
        for request in requests:
            self.assertEqual(Request.objects.get(pk=request.id).state, 'CANCELED')

    def test_cancel_pending_rg_some_requests_not_pending(self, modify_mock):
        requestgroup = mixer.blend(RequestGroup, state='PENDING', proposal=self.proposal,
                                   observation_type=RequestGroup.NORMAL)
        pending_r = mixer.blend(Request, state='PENDING', request_group=requestgroup)
        mixer.blend(Configuration, request=pending_r, instrument_type='1M0-SCICAM-SBIG')
        completed_r = mixer.blend(Request, state='COMPLETED', request_group=requestgroup)
        mixer.blend(Configuration, request=completed_r, instrument_type='1M0-SCICAM-SBIG')
        we_r = mixer.blend(Request, state='WINDOW_EXPIRED', request_group=requestgroup)
        mixer.blend(Configuration, request=we_r, instrument_type='1M0-SCICAM-SBIG')
        response = self.client.post(reverse('api:request_groups-cancel', kwargs={'pk': requestgroup.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestGroup.objects.get(pk=requestgroup.id).state, 'CANCELED')
        self.assertEqual(Request.objects.get(pk=pending_r.id).state, 'CANCELED')
        self.assertEqual(Request.objects.get(pk=completed_r.id).state, 'COMPLETED')
        self.assertEqual(Request.objects.get(pk=we_r.id).state, 'WINDOW_EXPIRED')

    def test_cannot_cancel_expired_rg(self, modify_mock):
        requestgroup = mixer.blend(RequestGroup, state='WINDOW_EXPIRED', proposal=self.proposal,
                                   observation_type=RequestGroup.NORMAL)
        expired_r = mixer.blend(Request, state='WINDOW_EXPIRED', request_group=requestgroup)
        response = self.client.post(reverse('api:request_groups-cancel', kwargs={'pk': requestgroup.id}))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RequestGroup.objects.get(pk=requestgroup.id).state, 'WINDOW_EXPIRED')
        self.assertEqual(Request.objects.get(pk=expired_r.id).state, 'WINDOW_EXPIRED')

    def test_cannot_cancel_completed_rg(self, modify_mock):
        requestgroup = mixer.blend(RequestGroup, state='COMPLETED', proposal=self.proposal,
                                   observation_type=RequestGroup.NORMAL)
        completed_r = mixer.blend(Request, state='COMPLETED', request_group=requestgroup)
        expired_r = mixer.blend(Request, state='WINDOW_EXPIRED', request_group=requestgroup)
        response = self.client.post(reverse('api:request_groups-cancel', kwargs={'pk': requestgroup.id}))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RequestGroup.objects.get(pk=requestgroup.id).state, 'COMPLETED')
        self.assertEqual(Request.objects.get(pk=expired_r.id).state, 'WINDOW_EXPIRED')
        self.assertEqual(Request.objects.get(pk=completed_r.id).state, 'COMPLETED')


@patch('observation_portal.common.state_changes.modify_ipp_time_from_requests')
class TestSchedulableRequestsApi(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()

        self.proposal = mixer.blend(Proposal)
        self.user = blend_user(user_params={'is_staff': True})
        mixer.blend(Membership, user=self.user, proposal=self.proposal, ipp_value=1.0)
        semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0,
            ipp_time_available=5.0
        )
        self.time_allocation_2m0 = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=semester, std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0,
            instrument_type='2M0-FLOYDS-SCICAM'
        )

        # Add a few requests within the current semester
        self.rgs = mixer.cycle(10).blend(RequestGroup, proposal=self.proposal, submitter=self.user,
                                         observation_type='NORMAL', operator='MANY', state='PENDING')
        for rg in self.rgs:
            reqs = mixer.cycle(5).blend(Request, request_group=rg, state='PENDING')
            start = datetime(2016, 10, 1, tzinfo=timezone.utc)
            end = datetime(2016, 11, 1, tzinfo=timezone.utc)
            for req in reqs:
                mixer.blend(Window, request=req, start=start, end=end)
                start += timedelta(days=2)
                end += timedelta(days=2)
                conf = mixer.blend(Configuration, request=req, type='EXPOSE', instrument_type='1M0-SCICAM-SBIG')
                mixer.blend(InstrumentConfig, configuration=conf,  exposure_time=60, exposure_count=10,
                            optical_elements={'filter': 'air'}, bin_x=1, bin_y=1)
                mixer.blend(AcquisitionConfig, configuration=conf, )
                mixer.blend(GuidingConfig, configuration=conf, )
                mixer.blend(Target, configuration=conf, type='ICRS', dec=20, ra=34.4)
                mixer.blend(Location, request=req, telescope_class='1m0')
                mixer.blend(Constraints, configuration=conf, max_airmass=2.0, min_lunar_distance=30.0)

        self.client.force_login(self.user)

    def test_setting_time_range_with_no_requests(self, modify_mock):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        end = datetime(2020, 4, 1, tzinfo=timezone.utc).isoformat()
        response = self.client.get(reverse('api:request_groups-schedulable-requests') + '?start=' + start + '&end=' + end)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_get_all_requests_in_semester(self, modify_mock):
        response = self.client.get(reverse('api:request_groups-schedulable-requests'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 10)
        tracking_numbers = [rg.id for rg in self.rgs]
        for rg in response.json():
            self.assertIn(rg['id'], tracking_numbers)

    def test_get_requests_for_telescope_class(self, modify_mock):
        # First add some 2m0 requests to the bunch
        rgs_2m0 = mixer.cycle(3).blend(RequestGroup, proposal=self.proposal, submitter=self.user,
                                        observation_type='NORMAL', operator='SINGLE', state='PENDING')
        start = datetime(2016, 10, 1, tzinfo=timezone.utc)
        end = datetime(2016, 11, 1, tzinfo=timezone.utc)
        for rg in rgs_2m0:
            req = mixer.blend(Request, request_group=rg, state='PENDING')
            mixer.blend(Window, request=req, start=start, end=end)
            start += timedelta(days=2)
            end += timedelta(days=2)
            conf = mixer.blend(Configuration, request=req, type='SPECTRUM', instrument_type='2M0-FLOYDS-SCICAM')
            mixer.blend(InstrumentConfig, configuration=conf,  exposure_time=60, exposure_count=10,
                        optical_elements={'slit': 'slit_6.0as'}, bin_x=1, bin_y=1)
            mixer.blend(AcquisitionConfig, configuration=conf, )
            mixer.blend(GuidingConfig, configuration=conf, )
            mixer.blend(Target, configuration=conf, type='ICRS', dec=20, ra=34.4)
            mixer.blend(Location, request=req, telescope_class='2m0')
            mixer.blend(Constraints, configuration=conf, max_airmass=2.0, min_lunar_distance=30.0)
        # Now get the requests filtered by each telescope_class and ensure its filtered properly
        rg_ids_numbers_1m0 = [rg.id for rg in self.rgs]        
        rg_ids_numbers_2m0 = [rg.id for rg in rgs_2m0]
        response_1m0 = self.client.get(reverse('api:request_groups-schedulable-requests') + '?telescope_class=1m0')
        self.assertEqual(response_1m0.status_code, 200)
        self.assertEqual(len(response_1m0.json()), 10)
        for rg in response_1m0.json():
            self.assertIn(rg['id'], rg_ids_numbers_1m0)

        response_2m0 = self.client.get(reverse('api:request_groups-schedulable-requests') + '?telescope_class=2m0')
        self.assertEqual(response_2m0.status_code, 200)
        self.assertEqual(len(response_2m0.json()), 3)
        for rg in response_2m0.json():
            self.assertIn(rg['id'], rg_ids_numbers_2m0)
        # And getting requests without specifying telescope_class gets all of them still
        response_no_filter = self.client.get(reverse('api:request_groups-schedulable-requests'))
        self.assertEqual(response_no_filter.status_code, 200)
        self.assertEqual(len(response_no_filter.json()), 13)
        combined_rg_ids = rg_ids_numbers_1m0 + rg_ids_numbers_2m0
        for rg in response_no_filter.json():
            self.assertIn(rg['id'], combined_rg_ids)

    def test_dont_get_requests_in_terminal_states(self, modify_mock):
        tracking_numbers = []
        # Set half the user requests to complete
        for rg in self.rgs:
            if rg.id % 2 == 0:
                for r in rg.requests.all():
                    r.state = 'COMPLETED'
                    r.save()
                rg.state = 'COMPLETED'
                rg.save()
            else:
                tracking_numbers.append(rg.id)

        # get all the requestgroups for the semester
        response = self.client.get(reverse('api:request_groups-schedulable-requests'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 5)
        for rg in response.json():
            self.assertIn(rg['id'], tracking_numbers)

    def test_dont_get_requests_in_inactive_proposals(self, modify_mock):
        self.proposal.active = False
        self.proposal.save()

        # get all the requestgroups for the semester
        response = self.client.get(reverse('api:request_groups-schedulable-requests'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_get_rg_if_any_requests_in_time_range(self, modify_mock):
        start = datetime(2016, 10, 8, tzinfo=timezone.utc).isoformat()
        end = datetime(2016, 11, 8, tzinfo=timezone.utc).isoformat()
        response = self.client.get(reverse('api:request_groups-schedulable-requests') + '?start=' + start + '&end=' + end)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 10)
        for rg in response.json():
            self.assertEqual(len(rg['requests']), 5)

    def test_not_admin(self, modify_mock):
        user = blend_user()
        self.client.force_login(user)
        response = self.client.get(reverse('api:request_groups-schedulable-requests'))
        self.assertEqual(response.status_code, 403)


class TestContention(APITestCase):
    def setUp(self):
        super().setUp()
        request = mixer.blend(Request, state='PENDING')
        mixer.blend(
            Window, start=timezone.now(), end=timezone.now() + timedelta(days=30), request=request
        )
        mixer.blend(Location, request=request)
        conf = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG', request=request)
        mixer.blend(Target, ra=15.0, type='ICRS', configuration=conf)
        mixer.blend(InstrumentConfig, configuration=conf)
        mixer.blend(AcquisitionConfig, configuration=conf)
        mixer.blend(GuidingConfig, configuration=conf)
        mixer.blend(Constraints, configuration=conf)
        self.request = request

    def test_contention_no_auth(self):
        response = self.client.get(
            reverse('api:contention', kwargs={'instrument_type': '1M0-SCICAM-SBIG'})
        )
        self.assertNotEqual(response.json()['contention_data'][1]['All Proposals'], 0)
        self.assertEqual(response.json()['contention_data'][2]['All Proposals'], 0)

    def test_contention_staff(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(
           reverse('api:contention', kwargs={'instrument_type': '1M0-SCICAM-SBIG'})
        )
        self.assertNotEqual(response.json()['contention_data'][1][self.request.request_group.proposal.id], 0)
        self.assertNotIn(self.request.request_group.proposal.id, response.json()['contention_data'][2])


class TestPressure(APITestCase):
    def setUp(self):
        super().setUp()

        self.now = datetime(year=2017, month=5, day=12, hour=10, tzinfo=timezone.utc)

        self.timezone_patch = patch('observation_portal.requestgroups.contention.timezone')
        self.mock_timezone = self.timezone_patch.start()
        self.mock_timezone.now.return_value = self.now

        self.site_intervals_patch = patch('observation_portal.requestgroups.contention.get_site_rise_set_intervals')
        self.mock_site_intervals = self.site_intervals_patch.start()

        for i in range(24):
            requestgroup = mixer.blend(RequestGroup, observation_type=RequestGroup.NORMAL)
            request = mixer.blend(Request, request_group=requestgroup, state='PENDING')
            mixer.blend(
                Window, start=timezone.now(), end=timezone.now() + timedelta(hours=i), request=request
            )
            conf = mixer.blend(Configuration, instrument_type='1M0-SCICAM-SBIG', request=request)
            mixer.blend(
                Target, ra=random.randint(0, 360), dec=random.randint(-180, 180),
                proper_motion_ra=0.0, proper_motion_dec=0.0, type='ICRS', configuration=conf
            )
            mixer.blend(Location, request=request)
            mixer.blend(Constraints, configuration=conf)
            mixer.blend(InstrumentConfig, configuration=conf)
            mixer.blend(AcquisitionConfig, configuration=conf)
            mixer.blend(GuidingConfig, configuration=conf)

    def tearDown(self):
        self.timezone_patch.stop()
        self.site_intervals_patch.stop()

    def test_pressure_no_auth(self):
        response = self.client.get(reverse('api:pressure'))
        self.assertEqual(len(response.json()['pressure_data']), 24 * 4)
        self.assertIn('All Proposals', response.json()['pressure_data'][0])
        self.assertIn('pressure_data', response.json())
        self.assertIn('site_nights', response.json())
        self.assertIn('site', response.json())
        self.assertIn('instrument_type', response.json())

    def test_pressure_auth(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(reverse('api:pressure'))
        self.assertNotIn('All Proposals', response.json()['pressure_data'][0])

    def test_get_site_data_should_get_one_site(self):
        pressure = Pressure(site='tst')
        self.assertEqual(len(pressure.sites), 1)

    def test_site_data_should_get_all_sites(self):
        pressure = Pressure(site='')
        self.assertEqual(len(pressure.sites), 2)

    def test_site_nights_ends_before_now(self):
        self.mock_site_intervals.return_value = [
            [self.now - timedelta(hours=10), self.now - timedelta(hours=1)]
        ]
        self.assertEqual(len(Pressure(site='tst')._site_nights()), 0)

    def test_site_nights_starts_before_now_ends_before_24hrs_from_now(self):
        self.mock_site_intervals.return_value = [
            [self.now - timedelta(hours=1), self.now + timedelta(hours=1)]
        ]
        returned = Pressure(site='tst')._site_nights()
        expected = [dict(name='tst', start=0, stop=1)]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned, expected)

    def test_site_nights_starts_after_now_ends_before_24hrs_from_now(self):
        self.mock_site_intervals.return_value = [
            [self.now + timedelta(hours=1), self.now + timedelta(hours=10)]
        ]
        returned = Pressure(site='tst')._site_nights()
        expected = [dict(name='tst', start=1, stop=10)]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned, expected)

    def test_site_nights_starts_after_now_ends_after_24hrs_from_now(self):
        self.mock_site_intervals.return_value = [
            [self.now + timedelta(hours=10), self.now + timedelta(hours=25)]
        ]
        returned = Pressure(site='tst')._site_nights()
        expected = [dict(name='tst', start=10, stop=24)]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned, expected)

    def test_site_nights_starts_after_24hrs_from_now(self):
        self.mock_site_intervals.return_value = [
            [self.now + timedelta(hours=25), self.now + timedelta(hours=26)]
        ]
        returned = Pressure(site='tst')._site_nights()
        self.assertEqual(len(returned), 0)

    def test_n_possible_telescopes_should_be_none_possible(self):
        intervals = {
            'tst': [(self.now + timedelta(hours=2), self.now + timedelta(hours=4))],
            'non': [(self.now + timedelta(hours=4), self.now + timedelta(hours=6))]
        }
        expected = 0
        returned = Pressure()._n_possible_telescopes(self.now + timedelta(hours=5), intervals, '1M0-SCICAM-SBIG')
        self.assertEqual(returned, expected)

    def test_n_possible_telescopes_should_be_some_possible(self):
        intervals = {
            'tst': [(self.now + timedelta(hours=2), self.now + timedelta(hours=4))],
            'non': [(self.now + timedelta(hours=4), self.now + timedelta(hours=6))]
        }
        expected = 2
        returned = Pressure()._n_possible_telescopes(self.now + timedelta(hours=3), intervals, '1M0-SCICAM-SBIG')
        self.assertEqual(returned, expected)

    def test_telescopes_for_instrument_type(self):
        p = Pressure()
        # Check that 1M0-SCICAM-SBIG is added to the telescopes dict, and it's the only thing in there.
        p._telescopes('1M0-SCICAM-SBIG')
        self.assertEqual(len(p.telescopes), 1)
        self.assertIn('1M0-SCICAM-SBIG', p.telescopes)
        # Check that 2M0-FLOYDS-SCICAM is added to the telescopes dict, and that there are not two things in there.
        floyds_returned = p._telescopes('2M0-FLOYDS-SCICAM')
        self.assertEqual(len(p.telescopes), 2)
        self.assertIn('2M0-FLOYDS-SCICAM', p.telescopes)
        # Check that the correct telescopes are returned.
        self.assertEqual(floyds_returned, p.telescopes['2M0-FLOYDS-SCICAM'])

    @patch('observation_portal.requestgroups.contention.get_filtered_rise_set_intervals_by_site')
    def test_visible_intervals(self, mock_intervals):
        requestgroup = mixer.blend(RequestGroup, observation_type=RequestGroup.NORMAL)
        request = mixer.blend(Request, request_group=requestgroup, state='PENDING', duration=70*60)  # Request duration is 70 minutes.
        mixer.blend(Window, request=request)
        mixer.blend(Location, request=request, site='tst')
        conf = mixer.blend(Configuration, request=request)
        mixer.blend(InstrumentConfig, configuration=conf)
        mixer.blend(AcquisitionConfig, configuration=conf)
        mixer.blend(GuidingConfig, configuration=conf)
        mixer.blend(Target, configuration=conf)
        mixer.blend(Constraints, configuration=conf)

        mock_intervals.return_value = {'tst': [
            [self.now - timedelta(hours=6), self.now - timedelta(hours=2)],  # Sets before now.
            [self.now + timedelta(hours=2), self.now + timedelta(hours=6)],
            [self.now + timedelta(hours=8), self.now + timedelta(hours=12)],
            [self.now - timedelta(hours=1), self.now + timedelta(minutes=30)],  # Sets too soon after now.
            [self.now + timedelta(hours=14), self.now + timedelta(hours=15)]  # Duration longer than interval.
        ]}
        expected = {
            'tst': [
                (self.now + timedelta(hours=2), self.now + timedelta(hours=6)),
                (self.now + timedelta(hours=8), self.now + timedelta(hours=12))
            ]
        }
        returned = Pressure()._visible_intervals(request=request)
        self.assertEqual(returned, expected)

    def test_time_visible(self):
        intervals = {
            'tst': [
                (self.now + timedelta(hours=1), self.now + timedelta(hours=2)),
                (self.now + timedelta(hours=4), self.now + timedelta(hours=5))
            ],
            'non': [
                (self.now + timedelta(hours=1), self.now + timedelta(hours=2))
            ]
        }
        expected = 3 * 3600  # 3 hours.
        returned = Pressure()._time_visible(intervals)
        self.assertEqual(returned, expected)

    def test_anonymize(self):
        data = [
            {
                'proposal1': 1,
                'proposal2': 3,
            },
            {
                'proposal1': 4
            }
        ]
        expected = [
            {
                'All Proposals': 4
            },
            {
                'All Proposals': 4
            }
        ]
        self.assertEqual(Pressure()._anonymize(data), expected)

    @patch('observation_portal.requestgroups.contention.get_filtered_rise_set_intervals_by_site')
    def test_binned_pressure_by_hours_from_now_should_be_gtzero_pressure(self, mock_intervals):
        requestgroup = mixer.blend(RequestGroup, observation_type=RequestGroup.NORMAL)
        request = mixer.blend(Request, request_group=requestgroup, state='PENDING', duration=120*60)  # 2 hour duration.
        mixer.blend(Window, request=request)
        mixer.blend(Location, request=request, site='tst')
        conf = mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        mixer.blend(InstrumentConfig, configuration=conf)
        mixer.blend(AcquisitionConfig, configuration=conf)
        mixer.blend(GuidingConfig, configuration=conf)
        mixer.blend(Constraints, configuration=conf)
        mixer.blend(Target, configuration=conf)

        mock_intervals.return_value = {'tst': [
            [self.now + timedelta(hours=2), self.now + timedelta(hours=6)],
        ]}
        p = Pressure()
        p.requests = [request]
        sum_of_pressure = sum(sum(time.values()) for i, time in enumerate(p._binned_pressure_by_hours_from_now()))
        self.assertGreater(sum_of_pressure, 0)

    def test_binned_pressure_by_hours_from_now_should_be_zero_pressure(self):
        p = Pressure()
        p.requests = []
        sum_of_pressure = sum(sum(time.values()) for i, time in enumerate(p._binned_pressure_by_hours_from_now()))
        self.assertEqual(sum_of_pressure, 0)


class TestMaxIppRequestgroupApi(SetTimeMixin, APITestCase):
    ''' Test getting max ipp allowable of requestgroups via API.'''

    def setUp(self):
        super().setUp()
        self.proposal = mixer.blend(Proposal, id='temp')
        self.semester = mixer.blend(Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
                                    end=datetime(2016, 12, 31, tzinfo=timezone.utc))

        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10.0, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=1.0
        )
        self.time_allocation_0m4_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='0M4-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10.0, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=1.0
        )
        self.user = blend_user()
        mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.client.force_login(self.user)
        self.generic_payload = copy.deepcopy(generic_payload)

    def test_get_max_ipp_fail_bad_rg(self):
        bad_data = self.generic_payload.copy()
        del bad_data['proposal']
        response = self.client.post(reverse('api:request_groups-max-allowable-ipp'), bad_data)
        self.assertIn('proposal', response.json()['errors'])
        self.assertEqual(response.status_code, 200)

    def test_get_max_ipp_max_ipp_returned(self):
        from observation_portal.requestgroups.duration_utils import MAX_IPP_LIMIT, MIN_IPP_LIMIT
        good_data = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-max-allowable-ipp'), good_data)
        self.assertEqual(response.status_code, 200)

        ipp_dict = response.json()
        self.assertIn(self.semester.id, ipp_dict)
        self.assertEqual(
            MAX_IPP_LIMIT, ipp_dict[self.semester.id]['1M0-SCICAM-SBIG']['max_allowable_ipp_value']
        )
        self.assertEqual(
            MIN_IPP_LIMIT, ipp_dict[self.semester.id]['1M0-SCICAM-SBIG']['min_allowable_ipp_value']
        )

    def test_get_max_ipp_reduced_max_ipp(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = 90.0 * 60.0  # 90 minute exposure (1.0 ipp available)
        response = self.client.post(reverse('api:request_groups-max-allowable-ipp'), good_data)
        self.assertEqual(response.status_code, 200)
        ipp_dict = response.json()
        self.assertIn(self.semester.id, ipp_dict)
        # max ipp allowable is close to 1.0 ipp_available / 1.5 ~duration + 1.
        self.assertEqual(1.649, ipp_dict[self.semester.id]['1M0-SCICAM-SBIG']['max_allowable_ipp_value'])

    def test_get_max_ipp_rounds_down(self):
        good_data = self.generic_payload.copy()
        good_data['requests'][0]['configurations'][0]['instrument_configs'][0]['exposure_time'] = 90.0 * 60.0  # 90 minute exposure (1.0 ipp available)
        self.time_allocation_1m0_sbig.ipp_time_available = 1.33
        self.time_allocation_1m0_sbig.save()
        response = self.client.post(reverse('api:request_groups-max-allowable-ipp'), good_data)
        self.assertEqual(response.status_code, 200)
        ipp_dict = response.json()
        self.assertIn(self.semester.id, ipp_dict)
        # max ipp allowable is close to 1.0 ipp_available / 1.5 ~duration + 1.
        self.assertEqual(1.863, ipp_dict[self.semester.id]['1M0-SCICAM-SBIG']['max_allowable_ipp_value'])

    def test_get_max_ipp_no_ipp_available(self):
        good_data = self.generic_payload.copy()
        good_data['ipp_value'] = 2.0
        self.time_allocation_1m0_sbig.ipp_time_available = 0.0
        self.time_allocation_1m0_sbig.save()
        response = self.client.post(reverse('api:request_groups-max-allowable-ipp'), good_data)
        self.assertEqual(response.status_code, 200)
        ipp_dict = response.json()
        self.assertIn(self.semester.id, ipp_dict)
        # max ipp allowable is close to 1.0 ipp_available / 1.5 ~duration + 1.
        self.assertEqual(1.0, ipp_dict[self.semester.id]['1M0-SCICAM-SBIG']['max_allowable_ipp_value'])


class TestFiltering(APITestCase):
    def test_requestgroup_filtering_works(self):
        proposal = mixer.blend(Proposal, public=True)
        mixer.blend(RequestGroup, name='filter on me', proposal=proposal, observation_type=RequestGroup.NORMAL)
        response = self.client.get(reverse('api:request_groups-list') + '?name=filter')
        self.assertEqual(response.json()['count'], 1)
        response = self.client.get(reverse('api:request_groups-list') + '?name=philbobaggins')
        self.assertEqual(response.json()['count'], 0)

    def test_request_filtering_works(self):
        proposal = mixer.blend(Proposal, public=True)
        rg = mixer.blend(RequestGroup, name='filter on me', proposal=proposal, observation_type=RequestGroup.NORMAL)
        request = mixer.blend(Request, state='PENDING', request_group=rg)
        create_simple_configuration(request=request)
        response = self.client.get(reverse('api:request_groups-list') + '?state=PENDING')
        self.assertEqual(response.json()['count'], 1)
        response = self.client.get(reverse('api:request_groups-list') + '?state=COMPLETED')
        self.assertEqual(response.json()['count'], 0)


class TestLastChanged(SetTimeMixin, APITestCase):
    def setUp(self):
        super().setUp()
        # Mock the cache with a real one for these tests
        self.locmem_cache = cache._create_cache('django.core.cache.backends.locmem.LocMemCache')
        self.locmem_cache.clear()
        self.patch1 = patch.object(views, 'cache', self.locmem_cache)
        self.patch1.start()
        self.patch2 = patch.object(state_changes, 'cache', self.locmem_cache)
        self.patch2.start()
        self.patch3 = patch.object(serializers, 'cache', self.locmem_cache)
        self.patch3.start()

        self.proposal = mixer.blend(Proposal)
        self.user = blend_user(user_params={'is_staff': True})
        self.client.force_login(self.user)
        self.semester = mixer.blend(
            Semester, id='2016B', start=datetime(2016, 9, 1, tzinfo=timezone.utc),
            end=datetime(2016, 12, 31, tzinfo=timezone.utc)
        )
        self.time_allocation_1m0_sbig = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='1M0-SCICAM-SBIG', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )
        self.time_allocation_2m0_floyds = mixer.blend(
            TimeAllocation, proposal=self.proposal, semester=self.semester,
            instrument_type='2M0-FLOYDS-SCICAM', std_allocation=100.0, std_time_used=0.0,
            rr_allocation=10, rr_time_used=0.0, ipp_limit=10.0, ipp_time_available=5.0
        )
        self.membership = mixer.blend(Membership, user=self.user, proposal=self.proposal)
        self.generic_payload = copy.deepcopy(generic_payload)
        self.generic_payload['proposal'] = self.proposal.id
        self.window = mixer.blend(Window, start=timezone.now() - timedelta(days=1), end=timezone.now() + timedelta(days=1))

    def tearDown(self):
        super().tearDown()
        self.patch1.stop()
        self.patch2.stop()
        self.patch3.stop()

    def test_last_change_date_is_7_days_out_if_no_cached_value(self):
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)

        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))

    def test_last_change_date_is_updated_when_request_is_submitted(self):
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)
        rg = self.generic_payload.copy()
        response = self.client.post(reverse('api:request_groups-list'), data=self.generic_payload)

        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now(), delta=timedelta(minutes=1))

    def test_last_change_date_is_not_updated_when_request_is_mixed(self):
        create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)
        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))

    def test_last_change_date_is_updated_when_request_changes_state_completed(self):
        requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)
        request = requestgroup.requests.first()
        request.state = 'COMPLETED'
        request.save()
        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now(), delta=timedelta(minutes=1))

    def test_last_change_date_is_updated_when_requestgroup_canceled(self):
        requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)
        requestgroup.state = 'CANCELED'
        requestgroup.save()
        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now(), delta=timedelta(minutes=1))

    def test_last_change_date_is_updated_when_configuration_status_failed(self):
        requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        request = requestgroup.requests.first()
        configuration = request.configurations.first()
        observation = mixer.blend(Observation, request=request)
        configuration_status = mixer.blend(ConfigurationStatus, observation=observation, configuration=configuration)
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)

        configuration_status.state = 'FAILED'
        configuration_status.save()

        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now(), delta=timedelta(minutes=1))

    def test_last_change_date_is_not_updated_when_configuration_status_attempted(self):
        requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        request = requestgroup.requests.first()
        configuration = request.configurations.first()
        observation = mixer.blend(Observation, request=request)
        configuration_status = mixer.blend(ConfigurationStatus, observation=observation, configuration=configuration)
        last_change_cached = self.locmem_cache.get('observation_portal_last_change_time')
        self.assertIsNone(last_change_cached)

        configuration_status.state = 'ATTEMPTED'
        configuration_status.save()

        response = self.client.get(reverse('api:last_changed'))
        last_change = response.json()['last_change_time']
        self.assertAlmostEqual(datetime_parser(last_change), timezone.now() - timedelta(days=7),
                               delta=timedelta(minutes=1))