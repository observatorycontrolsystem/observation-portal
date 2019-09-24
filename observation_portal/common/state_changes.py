from django.utils import timezone
from django.db import transaction
from django.db.models import F
from django.utils.translation import ugettext as _
from django.core.cache import cache

from observation_portal.proposals.models import TimeAllocation, TimeAllocationKey
from observation_portal.requestgroups.request_utils import exposure_completion_percentage
from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.observations.models import Observation

import logging
from math import isclose, floor

logger = logging.getLogger(__name__)

REQUEST_STATE_MAP = {
    'COMPLETED': ['PENDING', 'WINDOW_EXPIRED', 'CANCELED'],
    'WINDOW_EXPIRED': ['PENDING'],
    'CANCELED': ['PENDING'],
    'PENDING': []
}

TERMINAL_REQUEST_STATES = ['COMPLETED', 'CANCELED', 'WINDOW_EXPIRED']

TERMINAL_OBSERVATION_STATES = ['CANCELED', 'ABORTED', 'FAILED', 'COMPLETED']


class InvalidStateChange(Exception):
    """Raised when an illegal state change is attempted"""
    pass


class AggregateStateException(Exception):
    """Raised when we fail to aggregate request states into a request group state"""
    pass


class TimeAllocationError(Exception):
    """Raised when proposal time used goes above its allocation"""
    pass


def valid_request_state_change(old_state, new_state, obj):
    if old_state not in REQUEST_STATE_MAP[new_state]:
        raise InvalidStateChange(_(f'Cannot transition from request state {old_state} to {new_state} for {obj}'))


def on_configuration_status_state_change(instance):
    # Configuration Status state has changed, so do the necessary updates to the corresponding Observation,
    # Request, and RequestGroup
    if instance.observation.state not in TERMINAL_OBSERVATION_STATES:
        update_observation_state(instance.observation)

    if instance.observation.request.request_group.observation_type == RequestGroup.DIRECT:
        request_group_is_expired = False
    else:
        request_group_is_expired = instance.observation.request.request_group.max_window_time < timezone.now()

    update_request_state(
        instance.observation.request,
        instance.observation.configuration_statuses.all(),
        request_group_is_expired
    )
    update_request_group_state(instance.observation.request.request_group)


def on_request_state_change(old_request_state, new_request):
    if old_request_state == new_request.state:
        return
    cache.set('observation_portal_last_change_time', timezone.now(), None)
    valid_request_state_change(old_request_state, new_request.state, new_request)
    # Must be a valid transition, so do ipp time accounting here if it is a normal type observation
    if new_request.request_group.observation_type == RequestGroup.NORMAL:
        if new_request.state == 'COMPLETED':
            ipp_value = new_request.request_group.ipp_value
            if ipp_value < 1.0:
                modify_ipp_time_from_requests(ipp_value, [new_request], 'credit')
            else:
                if old_request_state == 'WINDOW_EXPIRED':
                    try:
                        modify_ipp_time_from_requests(ipp_value, [new_request], 'debit')
                    except TimeAllocationError as tae:
                        logger.warning(_(
                            f'Request {new_request} switched from WINDOW_EXPIRED to COMPLETED but did not have enough '
                            f'ipp_time to debit: {repr(tae)}'
                        ))
        if new_request.state == 'CANCELED' or new_request.state == 'WINDOW_EXPIRED':
            ipp_value = new_request.request_group.ipp_value
            if ipp_value >= 1.0:
                modify_ipp_time_from_requests(ipp_value, [new_request], 'credit')


def on_requestgroup_state_change(old_requestgroup_state, new_requestgroup):
    if old_requestgroup_state == new_requestgroup.state:
        return
    valid_request_state_change(old_requestgroup_state, new_requestgroup.state, new_requestgroup)
    if new_requestgroup.state in ['CANCELED', 'WINDOW_EXPIRED']:
        # Just because the RG is marked as completed, doesn't mean we should mark a pending R as completed
        for request in new_requestgroup.requests.filter(state__exact='PENDING'):
            request.state = new_requestgroup.state
            request.save()


def update_observation_state(observation):
    observation_state = get_observation_state(observation.configuration_statuses.all())

    if observation_state:
        with transaction.atomic():
            Observation.objects.filter(pk=observation.id).update(state=observation_state)

    if observation_state in ['FAILED', 'ABORTED']:
        # If the observation has failed, trigger a reschedule
        cache.set('observation_portal_last_change_time', timezone.now(), None)


def get_observation_state(configuration_statuses):
    states = [config_status.state for config_status in configuration_statuses]
    if all([state == 'PENDING' for state in states]):
        return 'PENDING'
    elif all([state == 'PENDING' or state == 'ATTEMPTED' for state in states]):
        return 'IN_PROGRESS'
    elif any([state == 'FAILED' for state in states]):
        return 'FAILED'
    elif any([state == 'ABORTED' for state in states]):
        return 'ABORTED'
    elif all([state == 'COMPLETED' for state in states]):
        return 'COMPLETED'
    return None


def validate_ipp(request_group_dict, total_duration_dict):
    ipp_value = request_group_dict['ipp_value'] - 1
    if ipp_value <= 0:
        return

    time_allocations_dict = {
        tak: TimeAllocation.objects.get(
            semester__id=tak.semester,
            instrument_type=tak.instrument_type,
            proposal__id=request_group_dict['proposal']
        ).ipp_time_available for tak in total_duration_dict.keys()
    }
    for tak, duration in total_duration_dict.items():
        duration_hours = duration / 3600
        if time_allocations_dict[tak] < (duration_hours * ipp_value):
            max_ipp_allowable = (time_allocations_dict[tak] / duration_hours) + 1
            truncated_max_ipp_allowable = floor(max_ipp_allowable * 1000) / 1000
            msg = _((
                f"An IPP Value of {(ipp_value + 1)} requires more IPP time than you have available "
                f"for '{request_group_dict['observation_type']}' Observation with the {tak.instrument_type} . "
                f"Please lower your IPP Value to <= {truncated_max_ipp_allowable} and submit again."
            ))
            raise TimeAllocationError(msg)
        time_allocations_dict[tak] -= (duration_hours * ipp_value)


def debit_ipp_time(request_group):
    ipp_value = request_group.ipp_value - 1
    if ipp_value <= 0:
        return
    try:
        time_allocations = request_group.timeallocations
        time_allocations_dict = {
            TimeAllocationKey(ta.semester.id, ta.instrument_type): ta for ta in time_allocations.all()
        }
        total_duration_dict = request_group.total_duration
        for tak, duration in total_duration_dict.items():
            duration_hours = duration / 3600
            ipp_difference = ipp_value * duration_hours
            with transaction.atomic():
                TimeAllocation.objects.select_for_update().filter(id=time_allocations_dict[tak].id).update(
                    ipp_time_available=F('ipp_time_available') - ipp_difference)
    except Exception as e:
        logger.warning(_(
            f'Problem debiting ipp on creation for request_group {request_group.id} on proposal '
            f'{request_group.proposal.id}: {repr(e)}'
        ))


def modify_ipp_time_from_requests(ipp_val, requests_list, modification='debit'):
    ipp_value = ipp_val - 1
    if ipp_value == 0:
        return
    try:
        for request in requests_list:
            time_allocations = request.timeallocations
            for time_allocation in time_allocations:
                duration_hours = request.duration / 3600.0
                modified_time = 0
                if modification == 'debit':
                    modified_time -= (duration_hours * ipp_value)
                elif modification == 'credit':
                    modified_time += abs(ipp_value) * duration_hours
                if (modified_time + time_allocation.ipp_time_available) < 0:
                    logger.warning(_(
                        f'ipp debiting for request {request.id} would set ipp_time_available < 0. Time available after '
                        f'debiting will be capped at 0'
                    ))
                    modified_time = -time_allocation.ipp_time_available
                elif (modified_time + time_allocation.ipp_time_available) > time_allocation.ipp_limit:
                    logger.warning(_(
                        f'ipp crediting for request {request.id} would set ipp_time_available > ipp_limit. Time '
                        f'available after crediting will be capped at ipp_limit'
                    ))
                    modified_time = time_allocation.ipp_limit - time_allocation.ipp_time_available
                with transaction.atomic():
                    TimeAllocation.objects.select_for_update().filter(
                        id=time_allocation.id).update(ipp_time_available=F('ipp_time_available') + modified_time)
    except Exception as e:
        logger.warning(_(f'Problem {modification}ing ipp time for request {request.id}: {repr(e)}'))


def get_request_state_from_configuration_statuses(request_state, acceptability_threshold, configuration_statuses):
    """Determine request state from all the configuration statuses associated with one of the request's observations"""
    observation_state = get_observation_state(configuration_statuses)
    completion_percent = exposure_completion_percentage(configuration_statuses)
    if isclose(acceptability_threshold, completion_percent) or \
            completion_percent >= acceptability_threshold or \
            observation_state == 'COMPLETED':
        return 'COMPLETED'
    return request_state


def update_request_state(request, configuration_statuses, request_group_expired):
    """Update a request state given a set of configuration statuses for an observation of that request. Return
    True if the state changed, else False."""
    state_changed = False
    old_state = request.state

    if old_state == 'COMPLETED':
        return state_changed

    new_request_state = get_request_state_from_configuration_statuses(
        old_state, request.acceptability_threshold, configuration_statuses
    )

    # If the state is not a terminal state and the request group has expired, mark the request as expired
    if new_request_state not in TERMINAL_REQUEST_STATES and request_group_expired:
        new_request_state = 'WINDOW_EXPIRED'

    if new_request_state == old_state:
        return False

    with transaction.atomic():
        # Re-get the request and lock. If the new state is a valid state transition, set it on the request atomically.
        if (Request.objects.select_for_update().filter(
            pk=request.id, state__in=REQUEST_STATE_MAP[new_request_state]).update(
                state=new_request_state, modified=timezone.now())):
            state_changed = True

    if state_changed:
        on_request_state_change(old_state, Request.objects.get(pk=request.id))

    return state_changed


def aggregate_request_states(request_group):
    """Aggregate the state of the request group from all of its child request states"""
    request_states = [request.state for request in Request.objects.filter(request_group=request_group)]
    # Set the priority ordering - assume AND by default
    state_priority = ['WINDOW_EXPIRED', 'PENDING', 'COMPLETED', 'CANCELED']
    if request_group.operator == 'MANY':
        state_priority = ['PENDING', 'COMPLETED', 'WINDOW_EXPIRED', 'CANCELED']

    for state in state_priority:
        if state in request_states:
            return state

    raise AggregateStateException(f'Unable to Aggregate States: {request_states}')


def update_request_states_for_window_expiration():
    """Update the state of all requests and request_groups to WINDOW_EXPIRED if their last window has passed.
    Return True if any states changed, else False."""
    now = timezone.now()
    states_changed = False
    for request_group in RequestGroup.objects.exclude(state__in=TERMINAL_REQUEST_STATES):
        request_states_changed = False
        if request_group.observation_type != RequestGroup.DIRECT:
            for request in request_group.requests.filter(state='PENDING').prefetch_related('windows'):
                if request.max_window_time < now:
                    logger.info(f'Expiring request {request.id}', extra={'tags': {'request_num': request.id}})
                    with transaction.atomic():
                        if Request.objects.select_for_update().filter(pk=request.id, state='PENDING').update(state='WINDOW_EXPIRED'):
                            states_changed = True
                            request_states_changed = True
                    on_request_state_change('PENDING', Request.objects.get(pk=request.id))
        else:
            for request in request_group.requests.all().prefetch_related('observation_set'):
                if request.observation_set.first().end < now:
                    logger.info(f'Expiring DIRECT request {request.id}', extra={'tags': {'request_num': request.id}})
                    with transaction.atomic():
                        if Request.objects.select_for_update().filter(pk=request.id, state='PENDING').update(state='WINDOW_EXPIRED'):
                            states_changed = True
                            request_states_changed = True
                    on_request_state_change('PENDING', Request.objects.get(pk=request.id))
        if request_states_changed:
            update_request_group_state(request_group)
    return states_changed


def update_request_group_state(request_group):
    """Update the state of the request group if possible. Return True if the state changed, else False."""
    new_request_group_state = aggregate_request_states(request_group)
    requestgroup_state_changed = False
    old_state = request_group.state
    with transaction.atomic():
        if (RequestGroup.objects.select_for_update().filter(
            pk=request_group.id, state__in=REQUEST_STATE_MAP[new_request_group_state]).update(
                state=new_request_group_state, modified=timezone.now())):
            requestgroup_state_changed = True

    if requestgroup_state_changed:
        on_requestgroup_state_change(old_state, RequestGroup.objects.get(pk=request_group.id))

    return requestgroup_state_changed
