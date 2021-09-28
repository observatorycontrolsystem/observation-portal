from django.utils.translation import ugettext as _
from math import ceil, floor
from collections import defaultdict
from django.utils import timezone
from django.conf import settings
import logging

from observation_portal.proposals.models import TimeAllocationKey, Proposal, Semester
from observation_portal.common.utils import cache_function
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import (get_filtered_rise_set_intervals_by_site, get_largest_interval,
                                                      get_distance_between, get_rise_set_target)

logger = logging.getLogger(__name__)


PER_CONFIGURATION_STARTUP_TIME = 16.0   # per-configuration startup time, which encompasses initial pointing


@cache_function(duration=60)
def get_semesters():
    semesters = list(Semester.objects.all().order_by('-start'))
    return semesters


def get_semester_in(start_date, end_date):
    semesters = get_semesters()
    for semester in semesters:
        if start_date >= semester.start and end_date <= semester.end:
            return semester

    return None


def get_instrument_configuration_duration_per_exposure(instrument_configuration_dict, instrument_name):
    total_overhead_per_exp = configdb.get_exposure_overhead(instrument_name,
                                                            instrument_configuration_dict['mode'])
    duration_per_exp = instrument_configuration_dict['exposure_time'] + total_overhead_per_exp
    return duration_per_exp


def get_instrument_configuration_duration(instrument_config_dict, instrument_name):
    duration_per_exposure = get_instrument_configuration_duration_per_exposure(instrument_config_dict, instrument_name)
    return instrument_config_dict['exposure_count'] * duration_per_exposure


def get_configuration_duration(configuration_dict, request_overheads, include_front_padding=True):
    conf_duration = {}
    instrumentconf_durations = [{
        'duration': get_instrument_configuration_duration(
            ic, configuration_dict['instrument_type']
        )} for ic in configuration_dict['instrument_configs']
    ]
    conf_duration['instrument_configs'] = instrumentconf_durations
    if ('REPEAT' in configuration_dict['type'] and 'repeat_duration' in configuration_dict
            and configuration_dict['repeat_duration'] is not None):
        conf_duration['duration'] = configuration_dict['repeat_duration']
    else:
        conf_duration['duration'] = sum([icd['duration'] for icd in instrumentconf_durations])
        if include_front_padding:
            conf_duration['duration'] += request_overheads['config_front_padding']
    return conf_duration


def get_request_duration_dict(request_dict, is_staff=False):
    req_durations = {'requests': []}
    for req in request_dict:
        req_info = {'duration': get_total_request_duration(req)}
        conf_durations = []
        for conf in req['configurations']:
            request_overheads = configdb.get_request_overheads(conf['instrument_type'])
            conf_durations.append(get_configuration_duration(conf, request_overheads))
        req_info['configurations'] = conf_durations
        rise_set_intervals = get_filtered_rise_set_intervals_by_site(req, is_staff=is_staff)
        req_info['largest_interval'] = get_largest_interval(rise_set_intervals).total_seconds()
        req_durations['requests'].append(req_info)
    req_durations['duration'] = sum([req['duration'] for req in req_durations['requests']])

    return req_durations


def get_max_ipp_for_requestgroup(requestgroup_dict):
    proposal = Proposal.objects.get(pk=requestgroup_dict['proposal'])
    request_durations = get_requestgroup_duration(requestgroup_dict)
    ipp_dict = {}
    for tak, duration in request_durations.items():
        time_allocation = proposal.timeallocation_set.get(
            semester=tak.semester, instrument_types__contains=[tak.instrument_type]
        )
        duration_hours = duration / 3600.0
        ipp_available = time_allocation.ipp_time_available
        max_ipp_allowable = min((ipp_available / duration_hours) + 1.0, settings.MAX_IPP_VALUE)
        truncated_max_ipp_allowable = floor(max_ipp_allowable * 1000.0) / 1000.0
        if tak.semester not in ipp_dict:
            ipp_dict[tak.semester] = {}
        ipp_dict[tak.semester][tak.instrument_type] = {
            'ipp_time_available': ipp_available,
            'ipp_limit': time_allocation.ipp_limit,
            'request_duration': duration_hours,
            'max_allowable_ipp_value': truncated_max_ipp_allowable,
            'min_allowable_ipp_value': settings.MIN_IPP_VALUE
        }
    return ipp_dict


def get_requestgroup_duration(requestgroup_dict):
    duration_sum = {}
    for req in requestgroup_dict['requests']:
        duration_by_instrument_type = get_request_duration_by_instrument_type(req)
        for instrument_type, duration in duration_by_instrument_type.items():
            tak = get_time_allocation_key(
                instrument_type=instrument_type,
                min_window_time=min([w['start'] for w in req['windows']]),
                max_window_time=max([w['end'] for w in req['windows']])
            )
            if tak not in duration_sum:
                duration_sum[tak] = 0
            duration_sum[tak] += duration
    return duration_sum


def get_num_exposures(instrument_config_dict, instrument_name,  time_available):
    duration_per_exp = get_instrument_configuration_duration_per_exposure(instrument_config_dict, instrument_name)
    exposure_time = time_available.total_seconds()
    num_exposures = exposure_time // duration_per_exp
    if exposure_time % duration_per_exp == 0:
        num_exposures -= 1
    return max(1, num_exposures)


# TODO: implement this (distance between two targets in arcsec)
def get_slew_distance(target_dict1, target_dict2, start_time):
    '''
        Get the angular distance between two targets, in units of arcseconds
    :param target_dict1:
    :param target_dict2:
    :return:
    '''
    rs_target_1 = get_rise_set_target(target_dict1)
    rs_target_2 = get_rise_set_target(target_dict2)
    distance_between = get_distance_between(rs_target_1, rs_target_2, start_time)
    return distance_between.in_degrees() * 3600


def get_total_complete_configurations_duration(configurations_list, start_time, priority_after=-1):
    durations_by_instrument_type = get_complete_configurations_duration_by_instrument_type(
        configurations_list, start_time, priority_after
    )
    total_duration = 0
    for duration in durations_by_instrument_type.values():
        total_duration += duration

    return total_duration


def get_optical_change_duration(configuration_dict, request_overheads, previous_optical_elements):
    total_change_overhead = 0
    for inst_config in configuration_dict['instrument_configs']:
        optical_elements = inst_config.get('optical_elements', {})
        change_overhead = 0
        for oe_type, oe_value in optical_elements.items():
            if oe_type not in previous_optical_elements or oe_value != previous_optical_elements[oe_type]:
                if '{}s'.format(oe_type) in request_overheads['optical_element_change_overheads']:
                    change_overhead = max(request_overheads['optical_element_change_overheads']['{}s'.format(oe_type)], change_overhead)
        previous_optical_elements = optical_elements
        total_change_overhead += change_overhead

    return total_change_overhead


def get_complete_configurations_duration_by_instrument_type(configurations_list, start_time, priority_after=-1):
    previous_conf_type = ''
    previous_optical_elements = {}
    previous_instrument = ''
    previous_target = {}
    durations_by_instrument_type = defaultdict(float)
    for configuration_dict in configurations_list:
        duration = 0
        configuration_types = configdb.get_configuration_types(configuration_dict['instrument_type'])
        if configuration_dict['priority'] > priority_after:
            request_overheads = configdb.get_request_overheads(configuration_dict['instrument_type'])
            duration += get_configuration_duration(configuration_dict, request_overheads)['duration']
            # Add the instrument change time if the instrument has changed
            if previous_instrument != configuration_dict['instrument_type']:
                duration += request_overheads['instrument_change_overhead']
            previous_instrument = configuration_dict['instrument_type']

            # Now add in optical element change time if the set of optical elements has changed
            duration += get_optical_change_duration(configuration_dict, request_overheads, previous_optical_elements)
            previous_optical_elements = configuration_dict['instrument_configs'][-1].get('optical_elements', {})

            # Now add in the slew time between targets (configurations). Only Sidereal can be calculated based on position.
            if (
                    not previous_target
                    or previous_target['type'].upper() != 'ICRS'
                    or configuration_dict['target']['type'].upper() != 'ICRS'
            ):
                duration += request_overheads['maximum_slew_overhead']
            elif previous_target != configuration_dict['target']:
                duration += min(
                    max(get_slew_distance(previous_target, configuration_dict['target'], start_time)
                        * request_overheads['slew_rate'], request_overheads['minimum_slew_overhead']),
                    request_overheads['maximum_slew_overhead']
                )
            previous_target = configuration_dict['target']

            # Now add the Acquisition overhead if this request requires it
            if configuration_dict['acquisition_config']['mode'] != 'OFF':
                if configuration_dict['acquisition_config']['mode'] in request_overheads['acquisition_overheads']:
                    duration += request_overheads['acquisition_overheads'][configuration_dict['acquisition_config']['mode']]
                    if 'exposure_time' in configuration_dict['acquisition_config'] and configuration_dict['acquisition_config']['exposure_time']:
                        duration += configuration_dict['acquisition_config']['exposure_time']
                    else:
                        duration += request_overheads['default_acquisition_exposure_time']

            # Now add the Guiding overhead if this request requires it
            guide_optional = configuration_dict['guiding_config']['optional'] if 'optional' in configuration_dict['guiding_config'] \
                else True
            if configuration_dict['guiding_config']['mode'] != 'OFF' and not guide_optional:
                if configuration_dict['guiding_config']['mode'] in request_overheads['guiding_overheads']:
                    duration += request_overheads['guiding_overheads'][configuration_dict['guiding_config']['mode']]

            # Certain Configuration Types for certain Instrument Types will have a non-zero config_change_overhead.
            # For instance, this could account for Lamp startup times when first switching to an ARC or LAMP_FLAT configuration.
            if previous_conf_type != configuration_dict['type']:
                duration += configuration_types.get(configuration_dict['type'], {}).get('config_change_overhead', 0.0)
            previous_conf_type = configuration_dict['type']
        else:
            previous_conf_type = configuration_dict['type']
            previous_instrument = configuration_dict['instrument_type']
            previous_target = configuration_dict['target']
            previous_optical_elements = configuration_dict['instrument_configs'][-1].get('optical_elements', {})
        durations_by_instrument_type[configuration_dict['instrument_type']] += duration

    return durations_by_instrument_type


def get_total_request_duration(request_dict):
    durations_by_instrument_type = get_request_duration_by_instrument_type(request_dict)
    total_duration = 0
    for duration in durations_by_instrument_type.values():
        total_duration += duration
    total_duration = ceil(total_duration)
    return total_duration


@cache_function()
def get_request_duration_by_instrument_type(request_dict):
    # calculate the total time needed by the request, based on its instrument and exposures
    durations_by_instrument_type = defaultdict(float)
    start_time = (min([window['start'] for window in request_dict['windows']])
                  if 'windows' in request_dict and request_dict['windows'] else timezone.now())
    try:
        configurations = sorted(
            request_dict['configurations'], key=lambda x: x['priority'])
    except KeyError:
        configurations = request_dict['configurations']
    durations_by_instrument_type = get_complete_configurations_duration_by_instrument_type(
        configurations, start_time)

    # Add in the front_padding proportionally by instrument_type here
    # TODO: We should move front_padding to the telescope level rather than instrument_type so we don't need to
    # assign it's value proportionally to observation time used per instrument_type
    total_duration = 0.0
    for duration in durations_by_instrument_type.values():
        total_duration += duration
    for instrument_type in durations_by_instrument_type.keys():
        request_overheads = configdb.get_request_overheads(instrument_type)
        durations_by_instrument_type[instrument_type] += (durations_by_instrument_type[instrument_type] / total_duration) * request_overheads['observation_front_padding']

    return durations_by_instrument_type


def get_time_allocation(instrument_type, proposal_id, min_window_time, max_window_time):
    timeall = None
    try:
        timeall = Proposal.objects.get(pk=proposal_id).timeallocation_set.get(
            semester__start__lte=min_window_time,
            semester__end__gte=max_window_time,
            instrument_types__contains=[instrument_type])
    except Exception:
        logger.warn(_("proposal {0} has overlapping time allocations for {1}").format(proposal_id, instrument_type))
    return timeall


def get_time_allocation_key(instrument_type, min_window_time, max_window_time):
    semester = get_semester_in(min_window_time, max_window_time)
    return TimeAllocationKey(semester.id, instrument_type)


def get_total_duration_dict(requestgroup_dict):
    # In the case of a SINGLE request requestgroup, we can just return the requestgroup duration dict (tak -> duration)
    if requestgroup_dict['operator'] == 'SINGLE':
        return get_requestgroup_duration(requestgroup_dict)
    else:
        # This will contain each duration for a request for a tak in the requestgroup
        # This is needed to decide if we pick the max or sum them later depending on requestgroup operator
        all_durations_by_tak = {}
        total_duration = {}
        for request in requestgroup_dict['requests']:
            min_window_time = min([window['start'] for window in request['windows']])
            max_window_time = max([window['end'] for window in request['windows']])

            duration_by_instrument_type = get_request_duration_by_instrument_type(request)
            for instrument_type, duration in duration_by_instrument_type.items():
                tak = get_time_allocation_key(
                    instrument_type,
                    min_window_time,
                    max_window_time
                )
                if tak not in all_durations_by_tak:
                    all_durations_by_tak[tak] = []
                all_durations_by_tak[tak].append(ceil(duration))
        if requestgroup_dict['operator'] in ['MANY', 'ONEOF']:
            for tak in all_durations_by_tak.keys():
                total_duration[tak] = max(all_durations_by_tak[tak])
        elif requestgroup_dict['operator'] == 'AND':
            for tak in all_durations_by_tak.keys():
                total_duration[tak] = sum(all_durations_by_tak[tak])
        return total_duration
