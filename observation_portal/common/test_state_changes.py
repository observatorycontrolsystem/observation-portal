from django.test import TestCase
from mixer.backend.django import mixer as dmixer
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.core import mail
from django_dramatiq.test import DramatiqTestCase

from observation_portal.observations.signals.handlers import cb_configurationstatus_post_save
import observation_portal.observations.signals.handlers  # noqa
import observation_portal.requestgroups.signals.handlers  # noqa
from observation_portal.common.test_helpers import (
    create_simple_requestgroup, create_simple_many_requestgroup, create_simple_configuration, SetTimeMixin,
    disconnect_signal
)
from observation_portal.proposals.models import Proposal, Membership
from observation_portal.accounts.models import Profile
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.requestgroups.models import Request, RequestGroup, Window
from observation_portal.common.state_changes import (
    get_request_state_from_configuration_statuses,
    update_request_state, aggregate_request_states,
    update_request_states_for_window_expiration
)


class TestStateChanges(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.proposal = dmixer.blend(Proposal)
        self.user = dmixer.blend(User)
        dmixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)
        now = timezone.now()
        # Create a requestgroup with 3 requests, each request has 3 configurations with current windows and observations
        self.requestgroup = create_simple_many_requestgroup(user=self.user, proposal=self.proposal, n_requests=3)
        for request in self.requestgroup.requests.all():
            request.acceptability_threshold = 100
            request.save()
            window = request.windows.first()
            window.start = now - timedelta(days=1)
            window.end = now + timedelta(days=1)
            window.save()
            observation = dmixer.blend(
                Observation, request=request, state='PENDING', start=now - timedelta(minutes=30),
                end=now + timedelta(minutes=30)
            )
            create_simple_configuration(request=request)
            create_simple_configuration(request=request)
            for configuration in request.configurations.all():
                for instrument_config in configuration.instrument_configs.all():
                    instrument_config.exposure_time = 100
                    instrument_config.exposure_count = 10
                    instrument_config.save()
                configuration_status = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
                )
                dmixer.blend(Summary, configuration_status=configuration_status, time_completed=0)

    def test_observation_state_failed_if_any_config_status_failed(self):
        observation = self.requestgroup.requests.first().observation_set.first()
        for cs in observation.configuration_statuses.all():
            cs.state = 'FAILED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'FAILED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        for request in self.requestgroup.requests.all():
            request.refresh_from_db()
            self.assertEqual(request.state, 'PENDING')

    def test_observation_state_complete_if_all_config_statuses_complete(self):
        observation = self.requestgroup.requests.first().observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 1000
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'COMPLETED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_observation_state_pending_if_all_config_statuses_pending(self):
        observation = self.requestgroup.requests.first().observation_set.first()
        for cs in observation.configuration_statuses.all():
            cs.state = 'PENDING'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'PENDING')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['PENDING', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_observation_state_in_progress_if_config_status_pending_or_attempted(self):
        observation = self.requestgroup.requests.first().observation_set.first()
        cs = observation.configuration_statuses.first()
        cs.state = 'ATTEMPTED'
        cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'IN_PROGRESS')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['PENDING', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_request_state_completed_if_a_config_status_failed_but_acceptability_threshold_reached(self):
        request = self.requestgroup.requests.first()
        request.acceptability_threshold = 90
        request.save()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 900
            summary.save()
            cs.state = 'FAILED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'FAILED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_request_state_completed_if_a_config_status_completed_but_acceptability_threshold_not_reached(self):
        request = self.requestgroup.requests.first()
        request.acceptability_threshold = 90
        request.save()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 0.0
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'COMPLETED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_request_state_complete_if_was_expired_but_config_statuses_complete(self):
        request = self.requestgroup.requests.first()
        request.state = 'WINDOW_EXPIRED'
        request.save()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 1000
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'COMPLETED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_request_state_complete_if_was_canceled_but_config_status_complete(self):
        request = self.requestgroup.requests.first()
        request.state = 'CANCELED'
        request.save()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 1000
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        observation.refresh_from_db()
        self.requestgroup.refresh_from_db()
        self.assertEqual(observation.state, 'COMPLETED')
        self.assertEqual(self.requestgroup.state, 'PENDING')
        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_many_requestgroup_complete_if_all_requests_complete(self):
        for request in self.requestgroup.requests.all():
            observation = request.observation_set.first()
            for cs in observation.configuration_statuses.all():
                summary = cs.summary
                summary.time_completed = 1000
                summary.save()
                cs.state = 'COMPLETED'
                cs.save()
            observation.refresh_from_db()
            self.assertEqual(observation.state, 'COMPLETED')
            request.refresh_from_db()
            self.assertEqual(request.state, 'COMPLETED')
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')

    def test_many_requestgroup_complete_if_requests_expired_and_complete(self):
        r1 = self.requestgroup.requests.all()[0]
        r2 = self.requestgroup.requests.all()[1]
        r3 = self.requestgroup.requests.all()[2]
        r1.state = 'WINDOW_EXPIRED'
        r1.save()
        for request in [r2, r3]:
            observation = request.observation_set.first()
            for cs in observation.configuration_statuses.all():
                summary = cs.summary
                summary.time_completed = 1000
                summary.save()
                cs.state = 'COMPLETED'
                cs.save()
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        request_states = ['WINDOW_EXPIRED', 'COMPLETED', 'COMPLETED']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_many_requestgroup_complete_if_requests_canceled_and_complete(self):
        r1 = self.requestgroup.requests.all()[0]
        r2 = self.requestgroup.requests.all()[1]
        r3 = self.requestgroup.requests.all()[2]
        r1.state = 'CANCELED'
        r1.save()
        for request in [r2, r3]:
            observation = request.observation_set.first()
            for cs in observation.configuration_statuses.all():
                summary = cs.summary
                summary.time_completed = 1000
                summary.save()
                cs.state = 'COMPLETED'
                cs.save()
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        request_states = ['CANCELED', 'COMPLETED', 'COMPLETED']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_many_requestgroup_complete_if_expired_and_complete(self):
        self.requestgroup.state = 'WINDOW_EXPIRED'
        self.requestgroup.save()
        for request in self.requestgroup.requests.all():
            request.state = 'WINDOW_EXPIRED'
            request.save()
        request = self.requestgroup.requests.first()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 1000
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        request_states = ['COMPLETED', 'WINDOW_EXPIRED', 'WINDOW_EXPIRED']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])

    def test_many_requests_canceled_to_completed(self):
        self.requestgroup.state = 'CANCELED'
        self.requestgroup.save()
        for request in self.requestgroup.requests.all():
            request.state = 'CANCELED'
            request.save()
        request = self.requestgroup.requests.first()
        observation = request.observation_set.first()
        for cs in observation.configuration_statuses.all():
            summary = cs.summary
            summary.time_completed = 1000
            summary.save()
            cs.state = 'COMPLETED'
            cs.save()
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        request_states = ['COMPLETED', 'CANCELED', 'CANCELED']
        for i, request in enumerate(self.requestgroup.requests.all()):
            request.refresh_from_db()
            self.assertEqual(request.state, request_states[i])


class TestStateFromConfigurationStatuses(SetTimeMixin, DramatiqTestCase):
    def setUp(self):
        super().setUp()
        self.proposal = dmixer.blend(Proposal)
        self.user = dmixer.blend(User)
        dmixer.blend(Membership, user=self.user, proposal=self.proposal)
        dmixer.blend(Profile, user=self.user, notifications_enabled=True)
        self.client.force_login(self.user)
        self.now = timezone.now()
        self.window = dmixer.blend(Window, start=self.now - timedelta(days=1), end=self.now + timedelta(days=1))
        self.requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        self.request = self.requestgroup.requests.first()
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')

    def test_all_configuration_statuses_complete(self):
        self.request.state = 'COMPLETED'
        self.request.save()
        observation = dmixer.blend(
            Observation, request=self.request, start=self.now - timedelta(minutes=30),
            end=self.now - timedelta(minutes=20)
        )
        for configuration in self.request.configurations.all():
            cs = dmixer.blend(
                ConfigurationStatus, observation=observation, configuration=configuration, state='COMPLETED'
            )
            for inst_config in configuration.instrument_configs.all():
                inst_config.exposure_time = 100
                inst_config.exposure_count = 10
                inst_config.save()
            dmixer.blend(Summary, configuration_status=cs, time_completed=1000)
        request_state = get_request_state_from_configuration_statuses(
            self.request.state, 100, observation.configuration_statuses.all()
        )
        self.assertEqual(request_state, 'COMPLETED')

    def test_configuration_statuses_not_complete_or_failed_use_initial(self):
        observation = dmixer.blend(
            Observation, request=self.request, start=self.now - timedelta(minutes=30),
            end=self.now + timedelta(minutes=20)
        )
        for configuration in self.request.configurations.all():
            cs = dmixer.blend(
                ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
            )
            dmixer.blend(Summary, configuration_status=cs, time_completed=0)
        initial_state = 'INITIAL'
        request_state = get_request_state_from_configuration_statuses(
            initial_state, 100, observation.configuration_statuses.all()
        )
        self.assertEqual(request_state, initial_state)
        # requestgroup state is not completed, no email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_ongoinging_configuration_statuses_in_use_initial(self):
        observation = dmixer.blend(
            Observation, request=self.request, start=self.now + timedelta(minutes=20),
            end=self.now + timedelta(minutes=30)
        )
        for configuration in self.request.configurations.all():
            cs = dmixer.blend(
                ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
            )
            dmixer.blend(Summary, configuration_status=cs, time_completed=0)
        # Make another configuration whose status is failed
        failed_configuration = create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        completed_cs = dmixer.blend(
            ConfigurationStatus, observation=observation, configuration=failed_configuration, state='FAILED'
        )
        dmixer.blend(Summary, configuration_status=completed_cs, time_completed=0)
        initial_state = 'INITIAL'
        request_state = get_request_state_from_configuration_statuses(
            initial_state, 100, observation.configuration_statuses.all()
        )
        self.assertEqual(request_state, initial_state)
        # requestgroup state is not completed, no email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_configuration_statuses_failed_but_threshold_complete(self):
        observation = dmixer.blend(
            Observation, request=self.request, start=self.now - timedelta(minutes=30),
            end=self.now + timedelta(minutes=30)
        )
        for configuration in self.request.configurations.all():
            cs = dmixer.blend(ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED')
            for inst_config in configuration.instrument_configs.all():
                inst_config.exposure_time = 100
                inst_config.exposure_count = 10
                inst_config.save()
            dmixer.blend(Summary, configuration_status=cs, time_completed=900)
        initial_state = 'INITIAL'
        request_state = get_request_state_from_configuration_statuses(
            initial_state, 90, observation.configuration_statuses.all()
        )
        self.assertEqual(request_state, 'COMPLETED')
        # The requestgroup state changed to complete, so an email should be sent
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_configuration_statuses_failed_but_threshold_complete_multi(self):
        observation = dmixer.blend(
            Observation, request=self.request, start=self.now - timedelta(minutes=30),
            end=self.now + timedelta(minutes=30)
        )
        for configuration in self.request.configurations.all():
            cs = dmixer.blend(ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED')
            for inst_config in configuration.instrument_configs.all():
                inst_config.exposure_time = 10
                inst_config.exposure_count = 1
                inst_config.save()
            dmixer.blend(Summary, configuration_status=cs, time_completed=0)
        # Make another configuration whose status is completed, so that we reach the acceptability threshold
        completed_configuration = create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        completed_cs = dmixer.blend(
            ConfigurationStatus, observation=observation, configuration=completed_configuration, state='COMPLETED'
        )
        inst_config_completed = completed_configuration.instrument_configs.first()
        inst_config_completed.exposure_count = 10
        inst_config_completed.exposure_time = 100
        inst_config_completed.save()
        dmixer.blend(Summary, configuration_status=completed_cs, time_completed=1000)
        initial_state = 'INITIAL'
        request_state = get_request_state_from_configuration_statuses(
            initial_state, 95, observation.configuration_statuses.all()
        )
        self.assertEqual(request_state, 'COMPLETED')
        # The requestgroup state changed to complete, so an email should be sent
        self.requestgroup.refresh_from_db()
        self.assertEqual(self.requestgroup.state, 'COMPLETED')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.requestgroup.name, str(mail.outbox[0].message()))
        self.assertEqual(mail.outbox[0].to, [self.user.email])


class TestRequestState(SetTimeMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.proposal = dmixer.blend(Proposal)
        self.user = dmixer.blend(User)
        dmixer.blend(Profile, user=self.user)
        self.client.force_login(self.user)
        self.now = timezone.now()
        self.window = dmixer.blend(Window, start=self.now - timedelta(days=1), end=self.now + timedelta(days=1))
        self.requestgroup = create_simple_requestgroup(
            user=self.user, proposal=self.proposal, instrument_type='1M0-SCICAM-SBIG', window=self.window
        )
        self.request = self.requestgroup.requests.first()
        self.request.acceptability_threshold = 100
        self.request.save()
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        create_simple_configuration(request=self.request, instrument_type='1M0-SCICAM-SBIG')
        for configuration in self.request.configurations.all():
            for inst_config in configuration.instrument_configs.all():
                inst_config.exposure_time = 10
                inst_config.exposure_count = 10
                inst_config.save()

    def test_request_state_complete(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'COMPLETED'
            self.request.save()
            observation = dmixer.blend(Observation, request=self.request)
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(ConfigurationStatus, observation=observation, configuration=configuration)
                dmixer.blend(Summary, configuration_status=cs, time_completed=100)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'COMPLETED')

    def test_request_state_configuration_statuses_complete(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            observation = dmixer.blend(Observation, request=self.request)
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='COMPLETED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=100)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertTrue(state_changed)
            self.assertEqual(self.request.state, 'COMPLETED')

    def test_request_state_initial_state_expired(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'WINDOW_EXPIRED'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'WINDOW_EXPIRED')

    def test_request_state_initial_state_canceled(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'CANCELED'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'CANCELED')

    def test_request_state_initial_state_pending(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'PENDING')

    def test_request_state_initial_state_pending_ur_expired(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='PENDING'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertTrue(state_changed)
            self.assertEqual(self.request.state, 'WINDOW_EXPIRED')

    def test_request_state_configuration_status_failed_initial_state_expired(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'WINDOW_EXPIRED'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=10)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), True)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'WINDOW_EXPIRED')

    def test_request_state_configuration_status_failed_initial_state_canceled(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'CANCELED'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=10)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'CANCELED')

    def test_request_state_configuration_status_failed(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'PENDING')

    def test_request_state_configuration_status_failed_but_threshold_complete(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.acceptability_threshold = 90
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=90)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertTrue(state_changed)
            self.assertEqual(self.request.state, 'COMPLETED')

    def test_request_state_configuration_status_failed_but_threshold_complete_2(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.acceptability_threshold = 70
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            # Make another configuration whose status is completed, so that we reach the acceptability threshold
            completed_configuration = create_simple_configuration(
                request=self.request, instrument_type='1M0-SCICAM-SBIG'
            )
            completed_cs = dmixer.blend(
                ConfigurationStatus, observation=observation, configuration=completed_configuration, state='COMPLETED'
            )
            inst_config_completed = completed_configuration.instrument_configs.first()
            inst_config_completed.exposure_count = 10
            inst_config_completed.exposure_time = 100
            inst_config_completed.save()
            dmixer.blend(Summary, configuration_status=completed_cs, time_completed=1000)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertTrue(state_changed)
            self.assertEqual(self.request.state, 'COMPLETED')

    def test_request_state_configuration_status_failed_and_threshold_failed(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.acceptability_threshold = 95
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now + timedelta(minutes=30)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=90)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'PENDING')

    def test_request_state_configuration_status_failed_2(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now - timedelta(minutes=20)
            )
            for configuration in self.request.configurations.all():
                cs = dmixer.blend(
                    ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED'
                )
                dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'PENDING')

    def test_request_state_repeat_configuration_failed_and_threshold_failed(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.save()
            repeat_configuration = self.request.configurations.first()
            repeat_configuration.type = 'REPEAT_EXPOSE'
            repeat_configuration.repeat_duration = 2000
            repeat_configuration.save()

            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now - timedelta(minutes=20)
            )
            for configuration in self.request.configurations.all():
                if configuration.id == repeat_configuration.id:
                    cs = dmixer.blend(
                        ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED',
                    )
                    dmixer.blend(Summary, configuration_status=cs, time_completed=1000, start=observation.start,
                                 end=observation.start + timedelta(seconds=1000))
                else:
                    cs = dmixer.blend(
                        ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED',
                    )
                    dmixer.blend(Summary, configuration_status=cs, time_completed=0)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertFalse(state_changed)
            self.assertEqual(self.request.state, 'PENDING')

    def test_request_state_repeat_configuration_failed_but_threshold_reached(self):
        with disconnect_signal(post_save, cb_configurationstatus_post_save, ConfigurationStatus):
            self.request.state = 'PENDING'
            self.request.acceptability_threshold = 90
            self.request.save()
            repeat_configuration = self.request.configurations.last()
            repeat_configuration.type = 'REPEAT_EXPOSE'
            repeat_configuration.repeat_duration = 2000
            repeat_configuration.save()

            observation = dmixer.blend(
                Observation, request=self.request, start=self.now - timedelta(minutes=30),
                end=self.now - timedelta(minutes=20)
            )
            repeat_starts = observation.start + timedelta(seconds=300)
            for configuration in self.request.configurations.all():
                if configuration.id == repeat_configuration.id:
                    cs = dmixer.blend(
                        ConfigurationStatus, observation=observation, configuration=configuration, state='FAILED',
                    )
                    dmixer.blend(Summary, configuration_status=cs, time_completed=1999,
                                 start=repeat_starts, end=repeat_starts + timedelta(seconds=1999))
                else:
                    cs = dmixer.blend(
                        ConfigurationStatus, observation=observation, configuration=configuration, state='COMPLETED',
                    )
                    dmixer.blend(Summary, configuration_status=cs, time_completed=100)
            state_changed = update_request_state(self.request, observation.configuration_statuses.all(), False)
            self.request.refresh_from_db()
            self.assertTrue(state_changed)
            self.assertEqual(self.request.state, 'COMPLETED')


class TestAggregateRequestStates(TestCase):
    def test_many_all_complete(self):
        request_states = ['COMPLETED', 'COMPLETED', 'COMPLETED']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_any_pending(self):
        request_states = ['COMPLETED', 'CANCELED', 'PENDING']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'PENDING')

    def test_many_expired_and_complete(self):
        request_states = ['WINDOW_EXPIRED', 'COMPLETED', 'WINDOW_EXPIRED']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_canceled_and_complete(self):
        request_states = ['CANCELED', 'COMPLETED', 'CANCELED']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_all_canceled(self):
        request_states = ['CANCELED', 'CANCELED', 'CANCELED']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'CANCELED')

    def test_many_all_expired(self):
        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'WINDOW_EXPIRED']
        rg = dmixer.blend(RequestGroup, operator='MANY', observation_type=RequestGroup.NORMAL)
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)
        aggregate_state = aggregate_request_states(rg)
        self.assertEqual(aggregate_state, 'WINDOW_EXPIRED')


@patch('observation_portal.common.state_changes.modify_ipp_time_from_requests')
class TestExpireRequests(TestCase):
    def setUp(self):
        self.request_group = dmixer.blend(RequestGroup, state='PENDING', observation_type=RequestGroup.NORMAL)

    def test_request_is_set_to_expired(self, ipp_mock):
        request = dmixer.blend(Request, state='PENDING', request_group=self.request_group)
        dmixer.blend(
            Window, start=timezone.now() - timedelta(days=2), end=timezone.now() - timedelta(days=1), request=request
        )
        result = update_request_states_for_window_expiration()
        request.refresh_from_db()
        self.request_group.refresh_from_db()
        self.assertTrue(result)
        self.assertEqual(request.state, 'WINDOW_EXPIRED')
        self.assertEqual(self.request_group.state, 'WINDOW_EXPIRED')

    def test_request_is_not_set_to_expired(self, ipp_mock):
        request = dmixer.blend(Request, state='PENDING', request_group=self.request_group)
        dmixer.blend(
            Window, start=timezone.now() - timedelta(days=2), end=timezone.now() + timedelta(days=1), request=request
        )
        result = update_request_states_for_window_expiration()
        request.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(request.state, 'PENDING')

    def test_completed_request_is_not_set_to_expired(self, ipp_mock):
        request = dmixer.blend(Request, state='COMPLETED', request_group=self.request_group)
        dmixer.blend(
            Window, start=timezone.now() - timedelta(days=2), end=timezone.now() - timedelta(days=1), request=request
        )
        result = update_request_states_for_window_expiration()
        request.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(request.state, 'COMPLETED')

    def test_canceled_request_is_not_set_to_expired(self, ipp_mock):
        request = dmixer.blend(Request, state='CANCELED', request_group=self.request_group)
        dmixer.blend(
            Window, start=timezone.now() - timedelta(days=2), end=timezone.now() - timedelta(days=1), request=request
        )
        result = update_request_states_for_window_expiration()
        request.refresh_from_db()
        self.request_group.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(request.state, 'CANCELED')
