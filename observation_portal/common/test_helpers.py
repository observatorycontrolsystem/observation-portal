from django.conf import settings
from unittest.mock import patch
from datetime import datetime
from django.utils import timezone
from mixer.backend.django import mixer
import responses
import json
import os

from observation_portal.requestgroups.models import RequestGroup, Request, Window, Configuration, Constraints, Target, Location

CONFIGDB_TEST_FILE = os.path.join(settings.BASE_DIR, 'valhalla/common/test_data/configdb.json')
FILTERWHEELS_FILE = os.path.join(settings.BASE_DIR, 'valhalla/common/test_data/filterwheels.json')


class ConfigDBTestMixin(object):
    '''Mixin class to mock configdb calls'''
    def setUp(self):
        responses._default_mock.__enter__()
        responses.add(
            responses.GET, settings.CONFIGDB_URL + '/sites/',
            json=json.loads(open(CONFIGDB_TEST_FILE).read()), status=200
        )
        responses.add(
            responses.GET, settings.CONFIGDB_URL + '/filterwheels/',
            json=json.loads(open(FILTERWHEELS_FILE).read()), status=200
        )
        super().setUp()

    def tearDown(self):
        super().tearDown()
        responses._default_mock.__exit__(None, None, None)


class SetTimeMixin(object):
    def setUp(self):
        self.time_patcher = patch('observation_portal.requestgroups.serializers.timezone.now')
        self.mock_now = self.time_patcher.start()
        self.mock_now.return_value = datetime(2016, 9, 1, tzinfo=timezone.utc)
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.time_patcher.stop()


def create_simple_requestgroup(user, proposal, state='PENDING', request=None, window=None, molecule=None,
                              constraints=None, target=None, location=None):
    ur = mixer.blend(RequestGroup, state=state, submitter=user, proposal=proposal)

    if not request:
        request = mixer.blend(Request, user_request=ur)
    else:
        request.user_request = ur
        request.save()

    if not window:
        mixer.blend(Window, request=request)
    else:
        window.request = request
        window.save()

    if not molecule:
        mixer.blend(Configuration, request=request)
    else:
        molecule.request = request
        molecule.save()

    if not constraints:
        mixer.blend(Constraints, request=request)
    else:
        constraints.request = request
        constraints.save()

    if not target:
        mixer.blend(Target, request=request)
    else:
        target.request = request
        target.save()

    if not location:
        mixer.blend(Location, request=request)
    else:
        location.request = request
        location.save()

    return ur
