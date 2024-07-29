import logging
from datetime import timedelta
from django.db import transaction
from django.db.models import F
from observation_portal.requestgroups.duration_utils import get_configuration_duration
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.common.configdb import configdb
from observation_portal.proposals.models import TimeAllocation, Semester


logger = logging.getLogger()


def on_summary_update_time_accounting(current, instance):
    """ Whenever a summary is created or updated, do time accounting based on the completed time """
    observation_type = instance.configuration_status.observation.request.request_group.observation_type
    # No time accounting is done for Direct submitted observations
    if observation_type in RequestGroup.NON_SCHEDULED_TYPES:
        return

    current_config_time = timedelta(seconds=0)
    if current is not None:
        current_config_time = configuration_time_used(current, observation_type)
    new_config_time = configuration_time_used(instance, observation_type)
    time_difference = (new_config_time - current_config_time).total_seconds() / 3600.0

    debit_time(instance.configuration_status, observation_type, time_difference, new_config_time.total_seconds() / 3600.0)


def debit_time(configuration_status, observation_type, time_difference, new_time_charged):
    if time_difference:
        time_allocations = configuration_status.observation.request.timeallocations
        for time_allocation in time_allocations:
            if configuration_status.configuration.instrument_type in time_allocation.instrument_types:
                if observation_type == RequestGroup.NORMAL:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(std_time_used=F('std_time_used') + time_difference)
                        configuration_status.time_charged = new_time_charged
                        configuration_status.save()
                elif observation_type == RequestGroup.RAPID_RESPONSE:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(rr_time_used=F('rr_time_used') + time_difference)
                        configuration_status.time_charged = new_time_charged
                        configuration_status.save()
                elif observation_type == RequestGroup.TIME_CRITICAL:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(tc_time_used=F('tc_time_used') + time_difference)
                        configuration_status.time_charged = new_time_charged
                        configuration_status.save()
                else:
                    logger.warning(f'Failed to perform time accounting on configuration_status {configuration_status.id}. Observation Type'
                                   '{observation_type} was not valid')
                    continue



def refund_observation_time(observation, percentage_refund):
    """ Refunds a percentage of an observations time used back to its TimeAllocations.
        Returns the total time refunded in hours
    """
    hours_refunded = 0
    for configuration_status in observation.configuration_statuses.all():
        hours_refunded += refund_configuration_status_time(configuration_status, percentage_refund)
    return hours_refunded


def refund_configuration_status_time(configuration_status, percentage_refund):
    """ Refunds a percentage of a configuration_statuses time used back to its TimeAllocations.
        Time can only be refunded if it was charged for this observation, i.e. no double refunds.
        Returns the time refunded in hours (0.0 if no refund occured).
    """
    has_summary = hasattr(configuration_status, 'summary')
    if configuration_status.state == 'PENDING' or not has_summary or configuration_status.time_charged == 0.0:
        return 0.0
    observation_type = configuration_status.observation.request.request_group.observation_type
    config_time = configuration_time_used(configuration_status.summary, observation_type).total_seconds() / 3600.0
    refunded_time_charged = config_time - (config_time * percentage_refund)
    if refunded_time_charged < configuration_status.time_charged:
        # The time_difference here should be negative, which means time is added to the TimeAllocation
        time_difference = refunded_time_charged - configuration_status.time_charged
        debit_time(configuration_status, observation_type, time_difference, refunded_time_charged)
        return abs(time_difference)
    return 0.0


def configuration_time_used(summary, observation_type):
    """ Calculates the observation bounded time completed for time accounting purposes """
    configuration_time = timedelta(seconds=0)
    configuration_time += summary.end - summary.start

    if observation_type == RequestGroup.RAPID_RESPONSE:
        request_overheads = configdb.get_request_overheads(summary.configuration_status.configuration.instrument_type)
        base_duration = timedelta(
            seconds=get_configuration_duration(summary.configuration_status.configuration.as_dict(), request_overheads)['duration']
        )
        base_duration += timedelta(seconds=(request_overheads['observation_front_padding'] / len(summary.configuration_status.observation.request.configurations.all())))
        configuration_time = min(configuration_time, base_duration)

    return configuration_time


def debit_realtime_time_allocation(site, enclosure, telescope, proposal, hours):
    """ Attempts to debit the largest suitable time allocation for a real time observation
        If hours is negative, it will act as a credit rather than a debit.
    """
    allowable_instruments = configdb.get_instruments_at_location(
        site, enclosure, telescope
    )
    instrument_types = allowable_instruments.get('types')
    max_time_allocation = None
    max_time_available = 0.0
    for ta in proposal.timeallocation_set.filter(semester=Semester.current_semesters().first()):
        for instrument_type in ta.instrument_types:
            if instrument_type.upper() in instrument_types:
                time_available = ta.realtime_allocation - ta.realtime_time_used
                if time_available > max_time_available:
                    max_time_available = time_available
                    max_time_allocation = ta
                continue
    if max_time_allocation:
        # If hours is negative, make sure we don't go below 0 time used
        max_time_allocation.realtime_time_used = max(max_time_allocation.realtime_time_used + hours, 0.0)
        max_time_allocation.save()
    else:
        logger.warning(f"Failed to find a time allocation to debit for RealTime submission on proposal {proposal.id} and telescope {telescope}.{enclosure}.{site}")
