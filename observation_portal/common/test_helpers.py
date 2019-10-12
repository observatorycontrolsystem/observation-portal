from unittest.mock import patch
from datetime import datetime
from django.utils import timezone
from mixer.backend.django import mixer

from observation_portal.requestgroups.models import (RequestGroup, Request, Window, Configuration, Constraints, Target,
                                                     Location, InstrumentConfig, GuidingConfig, AcquisitionConfig)


class SetTimeMixin(object):
    def setUp(self):
        self.time_patcher = patch('observation_portal.requestgroups.serializers.timezone.now')
        self.mock_now = self.time_patcher.start()
        self.mock_now.return_value = datetime(2016, 9, 1, tzinfo=timezone.utc)
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.time_patcher.stop()


class disconnect_signal(object):
    """Temporarily disconnect a model from a signal. Can use as a context manager."""
    def __init__(self, signal, receiver, sender, dispatch_uid=None):
        self.signal = signal
        self.receiver = receiver
        self.sender = sender
        self.dispatch_uid = dispatch_uid

    def __enter__(self):
        self.signal.disconnect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid
        )

    def __exit__(self, type, value, traceback):
        self.signal.connect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid
        )


def create_simple_requestgroup(user, proposal, state='PENDING', request=None, window=None, configuration=None,
                               constraints=None, target=None, location=None, instrument_config=None,
                               acquisition_config=None, guiding_config=None, instrument_type=None):
    rg = mixer.blend(RequestGroup, state=state, submitter=user, proposal=proposal,
                     observation_type=RequestGroup.NORMAL)

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

    if not location:
        mixer.blend(Location, request=request)
    else:
        location.request = request
        location.save()

    if not configuration:
        configuration = mixer.blend(Configuration, request=request, priority=1)
    else:
        configuration.request = request
        configuration.save()

    if instrument_type:
        configuration.instrument_type = instrument_type
        configuration.save()

    fill_in_configuration_structures(configuration, instrument_config, constraints, target,
                                                     acquisition_config, guiding_config)

    return rg


def create_simple_many_requestgroup(user, proposal, n_requests, state='PENDING'):
    operator = 'SINGLE' if n_requests == 1 else 'MANY'
    rg = mixer.blend(RequestGroup, state=state, submitter=user, proposal=proposal, operator=operator,
                     observation_type=RequestGroup.NORMAL)
    for _ in range(n_requests):
        request = mixer.blend(Request, request_group=rg, state=state)
        mixer.blend(Window, request=request)
        mixer.blend(Location, request=request)
        create_simple_configuration(request)
    return rg


def create_simple_configuration(request, instrument_type='1M0-SCICAM-SBIG', instrument_config=None, priority=1):
    configuration = mixer.blend(Configuration, request=request, instrument_type=instrument_type, priority=priority)
    fill_in_configuration_structures(configuration, instrument_config=instrument_config)
    return configuration


def fill_in_configuration_structures(configuration, instrument_config=None, constraints=None, target=None,
                               acquisition_config=None, guiding_config=None):
    if not constraints:
        mixer.blend(Constraints, configuration=configuration)
    else:
        constraints.configuration = configuration
        constraints.save()

    if not instrument_config:
        mixer.blend(InstrumentConfig, configuration=configuration, exposure_count=5, exposure_time=10)
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
        mixer.blend(Target, configuration=configuration, ra=11.1, dec=11.1)
    else:
        target.configuration = configuration
        target.save()