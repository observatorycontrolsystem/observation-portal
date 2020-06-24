from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from mixer.backend.django import mixer
from unittest.mock import patch

from observation_portal.accounts.test_utils import blend_user
from observation_portal.proposals.models import Proposal, Membership
from observation_portal.requestgroups.models import RequestGroup, Request, Configuration
from observation_portal.common.telescope_states import ElasticSearchException
from observation_portal.common.test_telescope_states import TelescopeStatesFromFile


class TestRequestGroupList(TestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposals = mixer.cycle(3).blend(Proposal)
        for proposal in self.proposals:
            mixer.blend(Membership, proposal=proposal, user=self.user)
        self.request_groups = mixer.cycle(3).blend(
            RequestGroup,
            proposal=(p for p in self.proposals)
        )
        self.requests = mixer.cycle(3).blend(
            Request,
            request_group=(rg for rg in self.request_groups),
        )
        self.client.force_login(self.user)

    def test_requestgroup_list(self):
        response = self.client.get(reverse('requestgroups:list'))
        for rg in self.request_groups:
            self.assertContains(response, rg.name)

    def test_requestgroup_no_auth(self):
        self.client.logout()
        response = self.client.get(reverse('requestgroups:list'))
        self.assertContains(response, 'Register an Account')

    def test_requestgroup_admin(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:list'))
        for rg in self.request_groups:
            self.assertNotContains(response, rg.name)

    def test_requestgroup_admin_staff_view_enabled(self):
        user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:list'))
        for rg in self.request_groups:
            self.assertContains(response, rg.name)

    def test_requestgroup_list_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        self.request_groups[0].submitter = self.user
        self.request_groups[0].save()
        response = self.client.get(reverse('requestgroups:list'))
        self.assertContains(response, self.request_groups[0].name)
        self.assertNotContains(response, self.request_groups[1].name)

    def test_no_other_requests(self):
        proposal = mixer.blend(Proposal)
        other_rg = mixer.blend(RequestGroup, proposal=proposal, name=mixer.RANDOM, observation_type=RequestGroup.NORMAL)
        response = self.client.get(reverse('requestgroups:list'))
        self.assertNotContains(response, other_rg.name)

    def test_filtering(self):
        response = self.client.get(
            reverse('requestgroups:list') + '?name={}'.format(self.request_groups[0].name)
        )
        self.assertContains(response, self.request_groups[0].name)
        self.assertNotContains(response, self.request_groups[1].name)
        self.assertNotContains(response, self.request_groups[2].name)


class TestRequestGroupDetail(TestCase):
    def setUp(self):
        super().setUp()
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM,
                                         observation_type=RequestGroup.NORMAL)
        self.requests = mixer.cycle(10).blend(Request, request_group=self.request_group)
        for request in self.requests:
            mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.user)

    def test_requestgroup_detail(self):
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        for request in self.requests:
            self.assertContains(response, request.id)

    def test_requestgroup_detail_no_auth(self):
        self.client.logout()
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        self.assertEqual(response.status_code, 404)

    def test_requestgroup_detail_admin(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        self.assertEqual(response.status_code, 404)

    def test_requestgroup_detail_admin_staff_view_enabled(self):
        user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        for request in self.requests:
            self.assertContains(response, request.id)

    def test_requestgroup_detail_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.user,
                                    observation_type=RequestGroup.NORMAL)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': request_group.id}))
        self.assertContains(response, request_group.name)

    def test_public_requestgroup_no_auth(self):
        proposal = mixer.blend(Proposal, public=True)
        self.request_group.proposal = proposal
        self.request_group.save()

        self.client.logout()
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        for request in self.requests:
            self.assertContains(response, request.id)

    def test_single_request_redirect(self):
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM,
                                    observation_type=RequestGroup.NORMAL)
        request = mixer.blend(Request, request_group=request_group)
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': request_group.id}))
        self.assertRedirects(response, reverse('requestgroups:request-detail', args=(request.id,)))


class TestRequestDetail(TestCase):
    def setUp(self):
        self.user = blend_user()
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM,
                                         observation_type=RequestGroup.NORMAL)
        self.request = mixer.blend(Request, request_group=self.request_group)
        mixer.blend(Configuration, request=self.request, instrument_type='1M0-SCICAM-SBIG')
        self.client.force_login(self.user)
        super().setUp()

    def test_request_detail(self):
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertContains(response, self.request.id)

    def test_request_detail_no_auth(self):
        self.client.logout()
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertEqual(response.status_code, 404)

    def test_request_detail_admin(self):
        user = blend_user(user_params={'is_staff': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertEqual(response.status_code, 404)

    def test_request_detail_admin_staff_view_enabled(self):
        user = blend_user(user_params={'is_staff': True}, profile_params={'staff_view': True})
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertContains(response, self.request.id)

    def test_request_detail_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.user,
                                    observation_type=RequestGroup.NORMAL)
        request = mixer.blend(Request, request_group=request_group)
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': request.id}))
        self.assertContains(response, request.id)

    def test_public_request_detail_no_auth(self):
        proposal = mixer.blend(Proposal, public=True)
        self.request_group.proposal = proposal
        self.request_group.save()

        self.client.logout()
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertContains(response, self.request.id)


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
