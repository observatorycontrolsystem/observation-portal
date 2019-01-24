from django.conf import settings
from unittest.mock import patch
from datetime import datetime
from django.utils import timezone
from mixer.backend.django import mixer
import responses
import json
import os

from observation_portal.requestgroups.models import (RequestGroup, Request, Window, Configuration, Constraints, Target,
                                                     Location, InstrumentConfig, GuidingConfig, AcquisitionConfig)

CONFIGDB_TEST_FILE = os.path.join(settings.BASE_DIR, 'observation_portal/common/test_data/configdb.json')
FILTERWHEELS_FILE = os.path.join(settings.BASE_DIR, 'observation_portal/common/test_data/filterwheels.json')


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


def create_simple_requestgroup(user, proposal, state='PENDING', request=None, window=None, configuration=None,
                               constraints=None, target=None, location=None, instrument_config=None,
                               acquisition_config=None, guiding_config=None):
    rg = mixer.blend(RequestGroup, state=state, submitter=user, proposal=proposal)

    if not request:
        request = mixer.blend(Request, request_group=rg)
    else:
        request.request_group = rg
        request.save()

    if not window:
        mixer.blend(Window, request=request)
    else:
        window.request = request
        window.save()

    if not configuration:
        configuration = mixer.blend(Configuration, request=request)
    else:
        configuration.request = request
        configuration.save()

    if not constraints:
        mixer.blend(Constraints, configuration=configuration)
    else:
        constraints.configuration = configuration
        constraints.save()

    if not instrument_config:
        mixer.blend(InstrumentConfig, configuration=configuration)
    else:
        instrument_config.configuration = configuration
        instrument_config.save()

    if not guiding_config:
        mixer.blend(GuidingConfig, configuration=configuration)
    else:
        guiding_config.configuration = configuration
        guiding_config.save()

    if not acquisition_config:
        mixer.blend(AcquisitionConfig, configuration=configuration)
    else:
        acquisition_config.configuration = configuration
        acquisition_config.save()

    if not target:
        mixer.blend(Target, configuration=configuration)
    else:
        target.configuration = configuration
        target.save()

    if not location:
        mixer.blend(Location, request=request)
    else:
        location.request = request
        location.save()

    return rg
