from datetime import timedelta
from django.db import transaction
from observation_portal.requestgroups.duration_utils import get_configuration_duration
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.common.configdb import configdb

import logging

logger = logging.getLogger()

@transaction.atomic
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
    time_difference = new_config_time - current_config_time

    if time_difference:
        with transaction.atomic():
            time_allocations = instance.configuration_status.observation.request.timeallocations.select_for_update()
            for time_allocation in time_allocations:
                if time_allocation.instrument_type.upper() == instance.configuration_status.configuration.instrument_type.upper():
                    if observation_type == RequestGroup.NORMAL:
                        time_used = timedelta(hours=time_allocation.std_time_used)
                        time_allocation.std_time_used = (time_used + time_difference).total_seconds() / 3600.0
                    elif observation_type == RequestGroup.RAPID_RESPONSE:
                        time_used = timedelta(hours=time_allocation.rr_time_used)
                        time_allocation.rr_time_used = (time_used + time_difference).total_seconds() / 3600.0
                    elif observation_type == RequestGroup.TIME_CRITICAL:
                        time_used = timedelta(hours=time_allocation.tc_time_used)
                        time_allocation.tc_time_used = (time_used + time_difference).total_seconds() / 3600.0
                    else:
                        logger.warning('Failed to perform time accounting on configuration_status {}. Observation Type'
                                       '{} was not valid'.format(instance.configuration_status.id, observation_type))
                        continue
                    time_allocation.save()


def configuration_time_used(summary, observation_type):
    """ Calculates the block bounded time completed for time accounting purposes """
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
