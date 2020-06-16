from datetime import timedelta
from django.db import transaction
from django.db.models import F
from observation_portal.requestgroups.duration_utils import get_configuration_duration
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.common.configdb import configdb
from observation_portal.proposals.models import TimeAllocation

import logging

logger = logging.getLogger()


def on_summary_update_time_accounting(current, instance):
    """ Whenever a summary is created or updated, do time accounting based on the completed time """
    observation_type = instance.configuration_status.observation.request.request_group.observation_type
    # No time accounting is done for Direct submitted observations
    if observation_type == RequestGroup.DIRECT:
        return

    current_config_time = timedelta(seconds=0)
    if current is not None:
        current_config_time = configuration_time_used(current, observation_type)
    new_config_time = configuration_time_used(instance, observation_type)
    time_difference = (new_config_time - current_config_time).total_seconds() / 3600.0

    if time_difference:
        time_allocations = instance.configuration_status.observation.request.timeallocations
        for time_allocation in time_allocations:
            if time_allocation.instrument_type.upper() == instance.configuration_status.configuration.instrument_type.upper():
                if observation_type == RequestGroup.NORMAL:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(std_time_used=F('std_time_used') + time_difference)
                elif observation_type == RequestGroup.RAPID_RESPONSE:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(rr_time_used=F('rr_time_used') + time_difference)
                elif observation_type == RequestGroup.TIME_CRITICAL:
                    with transaction.atomic():
                        TimeAllocation.objects.select_for_update().filter(
                            id=time_allocation.id).update(tc_time_used=F('tc_time_used') + time_difference)
                else:
                    logger.warning('Failed to perform time accounting on configuration_status {}. Observation Type'
                                   '{} was not valid'.format(instance.configuration_status.id, observation_type))
                    continue


def configuration_time_used(summary, observation_type):
    """ Calculates the observation bounded time completed for time accounting purposes """
    configuration_time = timedelta(seconds=0)
    configuration_time += summary.end - summary.start

    if observation_type == RequestGroup.RAPID_RESPONSE:
        base_duration = timedelta(
            seconds=get_configuration_duration(summary.configuration_status.configuration.as_dict())['duration']
        )
        request_overheads = configdb.get_request_overheads(summary.configuration_status.configuration.instrument_type)
        base_duration += timedelta(seconds=(request_overheads['front_padding'] / len(summary.configuration_status.observation.request.configurations.all())))
        configuration_time = min(configuration_time, base_duration)

    return configuration_time
