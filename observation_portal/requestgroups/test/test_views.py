from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from mixer.backend.django import mixer
from unittest.mock import patch

from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import Proposal, Membership
from observation_portal.requestgroups.models import RequestGroup, Request, Configuration
from observation_portal.common.telescope_states import ElasticSearchException
from observation_portal.common.test_telescope_states import TelescopeStatesFromFile


class TestRequestGroupList(TestCase):
    def setUp(self):
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
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
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:list'))
        for rg in self.request_groups:
            self.assertNotContains(response, rg.name)

    def test_requestgroup_admin_staff_view_enabled(self):
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user, staff_view=True)
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
        other_rg = mixer.blend(RequestGroup, proposal=proposal, name=mixer.RANDOM)
        response = self.client.get(reverse('requestgroups:list'))
        self.assertNotContains(response, other_rg.name)

    def test_filtering(self):
        response = self.client.get(
            reverse('requestgroups:list') + '?name={}'.format(self.request_groups[0].name)
        )
        self.assertContains(response, self.request_groups[0].name)
        self.assertNotContains(response, self.request_groups[1].name)
        self.assertNotContains(response, self.request_groups[2].name)


class TestUserrequestDetail(TestCase):
    def setUp(self):
        super().setUp()
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM)
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
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        self.assertEqual(response.status_code, 404)

    def test_requestgroup_detail_admin_staff_view_enabled(self):
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user, staff_view=True)
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': self.request_group.id}))
        for request in self.requests:
            self.assertContains(response, request.id)

    def test_requestgroup_detail_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.user)
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
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM)
        request = mixer.blend(Request, request_group=request_group)
        mixer.blend(Configuration, request=request, instrument_type='1M0-SCICAM-SBIG')
        response = self.client.get(reverse('requestgroups:detail', kwargs={'pk': request_group.id}))
        self.assertRedirects(response, reverse('requestgroups:request-detail', args=(request.id,)))


class TestRequestDetail(TestCase):
    def setUp(self):
        self.user = mixer.blend(User)
        mixer.blend(Profile, user=self.user)
        self.proposal = mixer.blend(Proposal)
        mixer.blend(Membership, proposal=self.proposal, user=self.user)
        self.request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM)
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
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user)
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertEqual(response.status_code, 404)

    def test_request_detail_admin_staff_view_enabled(self):
        user = mixer.blend(User, is_staff=True)
        mixer.blend(Profile, user=user, staff_view=True)
        self.client.force_login(user)
        response = self.client.get(reverse('requestgroups:request-detail', kwargs={'pk': self.request.id}))
        self.assertContains(response, self.request.id)

    def test_request_detail_only_authored(self):
        self.user.profile.view_authored_requests_only = True
        self.user.profile.save()
        request_group = mixer.blend(RequestGroup, proposal=self.proposal, name=mixer.RANDOM, submitter=self.user)
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
        self.user = mixer.blend(User)
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
    def test_instrument_information(self):
        response = self.client.get(reverse('api:instruments_information'))
        self.assertIn('1M0-SCICAM-SBIG', response.json())
