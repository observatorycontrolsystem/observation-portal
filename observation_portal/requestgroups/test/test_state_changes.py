from django.test import TestCase
from mixer.main import mixer
from mixer.backend.django import mixer as dmixer
from django.utils import timezone
from datetime import timedelta, datetime
from unittest.mock import patch

from observation_portal.requestgroups.models import Request, RequestGroup, Window
from observation_portal.requestgroups.state_changes import (
    get_request_state_from_pond_blocks, update_request_state, aggregate_request_states,
    update_request_states_from_pond_blocks, update_request_states_for_window_expiration
)


# TODO: Update these tests when we remove all pond stuff
class PondMolecule:
    completed = bool
    failed = bool
    request_num = int
    tracking_num = int
    exposure_time = float
    exposure_count = int
    events = list

    def _to_dict(self):
        return {'completed': self.completed, 'failed': self.failed, 'request_num': self.request_num,
                'tracking_num': self.tracking_num, 'events': self.events, 'exposure_time': self.exposure_time,
                'exposure_count': self.exposure_count}


class PondBlock:
    start = datetime
    end = datetime
    canceled = bool
    molecules = list

    def _to_dict(self):
        return {'start': self.start.isoformat(), 'end': self.end.isoformat(), 'canceled': self.canceled,
                'molecules': [m._to_dict() for m in self.molecules]}


class TestStateFromPondBlocks(TestCase):
    def test_pond_blocks_all_molecules_complete(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=True)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now-timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'

        pond_state = get_request_state_from_pond_blocks(initial_state, 100.0, pond_blocks)
        self.assertEqual(pond_state, 'COMPLETED')

    def test_pond_blocks_not_complete_or_failed_use_initial(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now+timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 100.0, pond_blocks)
        self.assertEqual(pond_state, initial_state)

    def test_pond_blocks_in_past_failed(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now-timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 100.0, pond_blocks)
        self.assertEqual(pond_state, 'FAILED')

    def test_pond_blocks_failed(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        molecules.append(mixer.blend(PondMolecule, completed=False, failed=True, events=[]))
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now+timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 100.0, pond_blocks)
        self.assertEqual(pond_state, 'FAILED')

    def test_pond_blocks_in_future_use_initial(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        molecules.append(mixer.blend(PondMolecule, completed=False, failed=True, events=[]))
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now + timedelta(minutes=30),
                                   end=now+timedelta(minutes=40))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 100.0, pond_blocks)
        self.assertEqual(pond_state, initial_state)

    def test_pond_blocks_failed_but_threshold_complete(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 9,}],
                                         exposure_time=100, exposure_count=10)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now + timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 90.0, pond_blocks)
        self.assertEqual(pond_state, 'COMPLETED')

    def test_pond_blocks_failed_and_threshold_failed(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 9,}],
                                         exposure_time=100, exposure_count=10)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now + timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 91.0, pond_blocks)
        self.assertEqual(pond_state, 'FAILED')

    def test_pond_blocks_failed_but_threshold_complete_multi(self):
        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 0,}],
                                         exposure_time=10, exposure_count=1)
        molecules.append(mixer.blend(PondMolecule, completed=True, failed=False, events=[{'completed_exposures': 10,}],
                                     exposure_time=100, exposure_count=10))
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now + timedelta(minutes=20))._to_dict()]

        initial_state = 'INITIAL'
        pond_state = get_request_state_from_pond_blocks(initial_state, 95.0, pond_blocks)
        self.assertEqual(pond_state, 'COMPLETED')


class TestRequestState(TestCase):
    def test_request_state_complete(self):
        request = dmixer.blend(Request, state='COMPLETED')

        molecules = mixer.cycle(4).blend(PondMolecule)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules)._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)
        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'COMPLETED')

    def test_request_state_pond_state_complete(self):
        request = dmixer.blend(Request, state='PENDING')

        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        complete_molecules = mixer.cycle(4).blend(PondMolecule, completed=True, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules)._to_dict(),
                       mixer.blend(PondBlock, molecules=complete_molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'COMPLETED')

    def test_request_state_pond_state_initial_state_expired(self):
        request = dmixer.blend(Request, state='WINDOW_EXPIRED')

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)

        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'WINDOW_EXPIRED')

    def test_request_state_pond_state_initial_state_canceled(self):
        request = dmixer.blend(Request, state='CANCELED')

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)

        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'CANCELED')

    def test_request_state_pond_state_initial_state_pending(self):
        request = dmixer.blend(Request, state='PENDING')
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, canceled=False, start=now - timedelta(minutes=30),
                                   end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'PENDING')
        self.assertEqual(fail_count, request.fail_count)

    def test_request_state_pond_state_initial_state_pending_ur_expired(self):
        request = dmixer.blend(Request, state='PENDING')

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'WINDOW_EXPIRED')

    def test_request_state_pond_state_failed_initial_state_expired(self):
        request = dmixer.blend(Request, state='WINDOW_EXPIRED')
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, True)

        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'WINDOW_EXPIRED')
        self.assertEqual(fail_count + 1, request.fail_count)

    def test_request_state_pond_state_failed_initial_state_canceled(self):
        request = dmixer.blend(Request, state='CANCELED')
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertFalse(state_changed)
        self.assertEqual(request.state, 'CANCELED')
        self.assertEqual(fail_count + 1, request.fail_count)

    def test_request_state_pond_state_failed(self):
        request = dmixer.blend(Request, state='PENDING')
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'PENDING')
        self.assertEqual(fail_count + 1, request.fail_count)

    def test_request_state_pond_state_failed_but_threshold_complete(self):
        request = dmixer.blend(Request, state='PENDING', acceptability_threshold=90.0)

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 9},],
                                         exposure_time=100, exposure_count=10)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'COMPLETED')

    def test_request_state_pond_state_failed_but_threshold_complete_2(self):
        request = dmixer.blend(Request, state='PENDING', acceptability_threshold=70.0)

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 0},],
                                         exposure_time=100, exposure_count=1)
        molecules.append(mixer.blend(PondMolecule, completed=True, failed=False, events=[{'completed_exposures': 10,}],
                                     exposure_time=100, exposure_count=10))
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'COMPLETED')

    def test_request_state_pond_state_failed_and_threshold_failed(self):
        request = dmixer.blend(Request, state='PENDING', acceptability_threshold=95.0)
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=True, events=[{'completed_exposures': 9},],
                                         exposure_time=100, exposure_count=10)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now + timedelta(minutes=30))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules)._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)

        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'PENDING')
        self.assertEqual(fail_count + 1, request.fail_count)

    def test_request_state_pond_state_failed_2(self):
        request = dmixer.blend(Request, state='PENDING')
        fail_count = request.fail_count

        now = timezone.now()
        molecules = mixer.cycle(4).blend(PondMolecule, completed=False, failed=False, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict(),
                       mixer.blend(PondBlock, molecules=molecules, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        state_changed = update_request_state(request, pond_blocks, False)
        request.refresh_from_db()
        self.assertTrue(state_changed)
        self.assertEqual(request.state, 'PENDING')
        self.assertEqual(fail_count + 1, request.fail_count)


class TestAggregateRequestStates(TestCase):
    def test_many_all_complete(self):
        request_states = ['COMPLETED', 'COMPLETED', 'COMPLETED']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_any_pending(self):
        request_states = ['COMPLETED', 'CANCELED', 'PENDING']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'PENDING')

    def test_many_expired_and_complete(self):
        request_states = ['WINDOW_EXPIRED', 'COMPLETED', 'WINDOW_EXPIRED']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_canceled_and_complete(self):
        request_states = ['CANCELED', 'COMPLETED', 'CANCELED']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_many_all_canceled(self):
        request_states = ['CANCELED', 'CANCELED', 'CANCELED']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'CANCELED')

    def test_many_all_expired(self):
        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'WINDOW_EXPIRED']
        rg = dmixer.blend(RequestGroup, operator='MANY')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'WINDOW_EXPIRED')

    def test_oneof_any_completed(self):
        request_states = ['WINDOW_EXPIRED', 'COMPLETED', 'PENDING']
        rg = dmixer.blend(RequestGroup, operator='ONEOF')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'COMPLETED')

    def test_oneof_pending_and_expired(self):
        request_states = ['WINDOW_EXPIRED', 'PENDING', 'PENDING']
        rg = dmixer.blend(RequestGroup, operator='ONEOF')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'PENDING')

    def test_oneof_all_expired(self):
        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'WINDOW_EXPIRED']
        rg = dmixer.blend(RequestGroup, operator='ONEOF')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'WINDOW_EXPIRED')

    def test_oneof_all_canceled(self):
        request_states = ['CANCELED', 'CANCELED', 'CANCELED']
        rg = dmixer.blend(RequestGroup, operator='ONEOF')
        dmixer.cycle(3).blend(Request, state=(state for state in request_states), request_group=rg)

        aggregate_state = aggregate_request_states(rg)

        self.assertEqual(aggregate_state, 'CANCELED')


@patch('observation_portal.requestgroups.state_changes.modify_ipp_time_from_requests')
class TestUpdateRequestStates(TestCase):
    def setUp(self):
        self.rg = dmixer.blend(RequestGroup, operator='MANY', state='PENDING')
        self.requests = dmixer.cycle(3).blend(Request, request_group=self.rg, state='PENDING')

    def test_many_requests_expire_after_last_window(self, modify_mock):
        now = timezone.now()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now-timedelta(days=1))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[0].id, tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[1].id, tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]), start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))
        pond_blocks = [pb._to_dict() for pb in pond_blocks]

        update_request_states_from_pond_blocks(pond_blocks)

        for req in self.requests:
            req.refresh_from_db()
            self.assertEqual(req.state, 'WINDOW_EXPIRED')
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'WINDOW_EXPIRED')

    def test_many_requests_complete_and_expired(self, modify_mock):
        now = timezone.now()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now-timedelta(days=1))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[0].id, tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[1].id, tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]), start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))
        pond_blocks = [pb._to_dict() for pb in pond_blocks]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['COMPLETED', 'WINDOW_EXPIRED', 'WINDOW_EXPIRED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_many_requests_complete_and_failed(self, modify_mock):
        now = timezone.now()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now+timedelta(days=1))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[0].id, tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[1].id, tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[2].id, tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]), start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))
        pond_blocks = [pb._to_dict() for pb in pond_blocks]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['COMPLETED', 'COMPLETED', 'PENDING']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'PENDING')

    def test_many_requests_window_expired_and_failed(self, modify_mock):
        now = timezone.now()
        self.requests[0].state = 'WINDOW_EXPIRED'
        self.requests[0].save()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now+timedelta(days=1))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[0].id, tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[1].id, tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[2].id, tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]), start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))
        pond_blocks = [pb._to_dict() for pb in pond_blocks]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['WINDOW_EXPIRED', 'PENDING', 'PENDING']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'PENDING')

    def test_many_requests_complete_and_complete(self, modify_mock):
        now = timezone.now()
        self.requests[0].state = 'COMPLETED'
        self.requests[0].save()
        self.requests[1].state = 'COMPLETED'
        self.requests[1].save()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now+timedelta(days=1))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['COMPLETED', 'COMPLETED', 'COMPLETED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_many_requests_complete_and_window_expired(self, modify_mock):
        now = timezone.now()
        self.requests[0].state = 'COMPLETED'
        self.requests[0].save()
        self.requests[1].state = 'COMPLETED'
        self.requests[1].save()
        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now-timedelta(days=1))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[2].id, tracking_num=self.rg.id, events=[])
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['COMPLETED', 'COMPLETED', 'WINDOW_EXPIRED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_many_requests_window_expired_to_completed(self, modify_mock):
        now = timezone.now()
        for req in self.requests:
            req.state = 'WINDOW_EXPIRED'
            req.save()

        self.rg.state = 'WINDOW_EXPIRED'
        self.rg.save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now-timedelta(days=1))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'COMPLETED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_many_requests_canceled_to_completed(self, modify_mock):
        now = timezone.now()
        for req in self.requests:
            req.state = 'CANCELED'
            req.save()

        self.rg.state = 'CANCELED'
        self.rg.save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now-timedelta(days=2), end=now-timedelta(days=1))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['CANCELED', 'CANCELED', 'COMPLETED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_oneof_requests_complete_one_and_done(self, modify_mock):
        now = timezone.now()
        self.rg.operator = 'ONEOF'
        self.rg.save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now - timedelta(days=2),
                              end=now + timedelta(days=1))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[0].id,
                                          tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[1].id,
                                          tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[2].id,
                                          tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]),
                                           start=now - timedelta(minutes=30), end=now + timedelta(minutes=20),
                                           canceled=False)
        pond_blocks = [pb._to_dict() for pb in pond_blocks]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['COMPLETED', 'PENDING', 'PENDING']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_oneof_requests_fail_and_window_expired(self, modify_mock):
        now = timezone.now()
        self.rg.operator = 'ONEOF'
        self.rg.save()
        self.requests[0].state = 'WINDOW_EXPIRED'
        self.requests[0].save()
        self.requests[1].state = 'WINDOW_EXPIRED'
        self.requests[1].save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now - timedelta(days=2),
                              end=(e for e in [now - timedelta(days=1), now - timedelta(days=1), now + timedelta(days=1)]))
        molecules1 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=False, request_num=self.requests[0].id,
                                          tracking_num=self.rg.id, events=[])
        molecules2 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[1].id,
                                          tracking_num=self.rg.id, events=[])
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=False, failed=True, request_num=self.requests[2].id,
                                          tracking_num=self.rg.id, events=[])
        pond_blocks = mixer.cycle(3).blend(PondBlock, molecules=(m for m in [molecules1, molecules2, molecules3]),
                                           start=now - timedelta(minutes=30), end=now - timedelta(minutes=20),
                                           canceled=False)
        pond_blocks = [pb._to_dict() for pb in pond_blocks]
        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'PENDING']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'PENDING')

    def test_oneof_requests_window_expired_to_completed(self, modify_mock):
        now = timezone.now()
        self.rg.operator = 'ONEOF'
        self.rg.save()
        for req in self.requests:
            req.state = 'WINDOW_EXPIRED'
            req.save()

        self.rg.state = 'WINDOW_EXPIRED'
        self.rg.save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now - timedelta(days=2),
                              end=(e for e in [now - timedelta(days=1), now - timedelta(days=1), now + timedelta(days=1)]))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['WINDOW_EXPIRED', 'WINDOW_EXPIRED', 'COMPLETED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')

    def test_oneof_requests_canceled_to_completed(self, modify_mock):
        now = timezone.now()
        self.rg.operator = 'ONEOF'
        self.rg.save()
        for req in self.requests:
            req.state = 'CANCELED'
            req.save()

        self.rg.state = 'CANCELED'
        self.rg.save()

        dmixer.cycle(3).blend(Window, request=(r for r in self.requests), start=now - timedelta(days=2),
                              end=(e for e in [now - timedelta(days=1), now - timedelta(days=1), now + timedelta(days=1)]))
        molecules3 = mixer.cycle(3).blend(PondMolecule, completed=True, failed=False, request_num=self.requests[2].id, tracking_num=self.rg.id)
        pond_blocks = [mixer.blend(PondBlock, molecules=molecules3, start=now - timedelta(minutes=30), end=now - timedelta(minutes=20))._to_dict()]

        update_request_states_from_pond_blocks(pond_blocks)

        request_states = ['CANCELED', 'CANCELED', 'COMPLETED']
        for i, req in enumerate(self.requests):
            req.refresh_from_db()
            self.assertEqual(req.state, request_states[i])
        self.rg.refresh_from_db()
        self.assertEqual(self.rg.state, 'COMPLETED')


@patch('observation_portal.requestgroups.state_changes.modify_ipp_time_from_requests')
class TestExpireRequests(TestCase):
    def setUp(self):
        self.request_group = dmixer.blend(RequestGroup, state='PENDING')

    def test_request_is_set_to_expired(self, ipp_mock):
        request = dmixer.blend(Request, state='PENDING', request_group=self.request_group)
        dmixer.blend(
            Window, start=timezone.now() - timedelta(days=2), end=timezone.now() - timedelta(days=1), request=request
        )

        result = update_request_states_for_window_expiration()
        request.refresh_from_db()
        self.assertTrue(result)
        self.assertEqual(request.state, 'WINDOW_EXPIRED')

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
