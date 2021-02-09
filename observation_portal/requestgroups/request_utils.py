from datetime import timedelta
from rise_set.angle import Angle
from rise_set.astrometry import calculate_airmass_at_times
import requests
import json

from observation_portal.common.configdb import configdb, ConfigDB
from observation_portal.common.telescope_states import TelescopeStates, filter_telescope_states_by_intervals
from observation_portal.common.rise_set_utils import get_rise_set_target, get_filtered_rise_set_intervals_by_site
from observation_portal.requestgroups.target_helpers import TARGET_TYPE_HELPER_MAP

# TODO: Use configuration types from configdb

MOLECULE_TYPE_DISPLAY = {
    'EXPOSE': 'Imaging',
    'REPEAT_EXPOSE': 'Repeat Imaging',
    'SKY_FLAT': 'Sky Flat',
    'STANDARD': 'Standard',
    'ARC': 'Arc',
    'LAMP_FLAT': 'Lamp Flat',
    'SPECTRUM': 'Spectrum',
    'REPEAT_SPECTRUM': 'Repeat Spectrum',
    'AUTO_FOCUS': 'Auto Focus',
    'TRIPLE': 'Triple',
    'NRES_TEST': 'NRES Test',
    'NRES_SPECTRUM': 'NRES Spectrum',
    'REPEAT_NRES_SPECTRUM': 'Repeat NRES Spectrum',
    'NRES_EXPOSE': 'NRES Expose',
    'ENGINEERING': 'Engineering',
    'SCRIPT': 'Script'
}


def get_telescope_states_for_request(request_dict, is_staff=False):
    # TODO: update to support multiple instruments in a list
    instrument_type = request_dict['configurations'][0]['instrument_type']
    site_intervals = {}
    only_schedulable = not (is_staff and ConfigDB.is_location_fully_set(request_dict.get('location', {})))
    # Build up the list of telescopes and their rise set intervals for the target on this request
    site_data = configdb.get_sites_with_instrument_type_and_location(
        instrument_type=instrument_type,
        site_code=request_dict['location']['site'] if 'site' in request_dict['location'] else '',
        enclosure_code=request_dict['location']['enclosure'] if 'enclosure' in request_dict['location'] else '',
        telescope_code=request_dict['location']['telescope'] if 'telescope' in request_dict['location'] else '',
        only_schedulable=only_schedulable
    )

    for site, details in site_data.items():
        if site not in site_intervals:
            site_intervals[site] = get_filtered_rise_set_intervals_by_site(request_dict, site=site, is_staff=is_staff).get(site, [])

    # If you have no sites, return the empty dict here
    if not site_intervals:
        return {}

    # Retrieve the telescope states for that set of sites
    min_window_time = min([window['start'] for window in request_dict['windows']])
    max_window_time = max([window['end'] for window in request_dict['windows']])
    telescope_states = TelescopeStates(
        start=min_window_time,
        end=max_window_time,
        sites=list(site_intervals.keys()),
        instrument_types=[instrument_type],
        location_dict=request_dict.get('location', {}),
        only_schedulable=only_schedulable
    ).get()
    # Remove the empty intervals from the dictionary
    site_intervals = {site: intervals for site, intervals in site_intervals.items() if intervals}

    # Filter the telescope states list with the site intervals
    filtered_telescope_states = filter_telescope_states_by_intervals(
        telescope_states, site_intervals, min_window_time, max_window_time
    )

    return filtered_telescope_states


def date_range_from_interval(start_time, end_time, dt=timedelta(minutes=15)):
    time = start_time
    while time < end_time:
        yield time
        time += dt


def get_airmasses_for_request_at_sites(request_dict, is_staff=False):
    data = {
        'airmass_data': {},
    }
    instrument_type = request_dict['configurations'][0]['instrument_type']
    constraints = request_dict['configurations'][0]['constraints']
    target = request_dict['configurations'][0]['target']
    target_type = str(target.get('type', '')).upper()
    only_schedulable = not (is_staff and ConfigDB.is_location_fully_set(request_dict.get('location', {})))

    if target_type in ['ICRS', 'ORBITAL_ELEMENTS'] and TARGET_TYPE_HELPER_MAP[target_type](target).is_valid():
        site_data = configdb.get_sites_with_instrument_type_and_location(
            instrument_type=instrument_type,
            site_code=request_dict['location'].get('site'),
            enclosure_code=request_dict['location'].get('enclosure'),
            telescope_code=request_dict['location'].get('telescope'),
            only_schedulable=only_schedulable
        )
        rs_target = get_rise_set_target(target)
        for site_id, site_details in site_data.items():
            night_times = []
            site_lat = Angle(degrees=site_details['latitude'])
            site_lon = Angle(degrees=site_details['longitude'])
            site_alt = site_details['altitude']
            intervals = get_filtered_rise_set_intervals_by_site(request_dict, site_id, is_staff=is_staff).get(site_id, [])
            for interval in intervals:
                night_times.extend(
                    [time for time in date_range_from_interval(interval[0], interval[1], dt=timedelta(minutes=10))])

            if len(night_times) > 0:
                if site_id not in data:
                    data['airmass_data'][site_id] = {
                        'times': [time.strftime('%Y-%m-%dT%H:%M') for time in night_times],
                    }

                # Need to average airmass values for set of unique targets in request
                unique_targets_constraints = set([json.dumps((configuration['target'], configuration['constraints'])) for configuration in request_dict['configurations']])
                unique_count = len(unique_targets_constraints)
                max_airmass = 0.0
                for target_constraints in unique_targets_constraints:
                    (target, constraints) = json.loads(target_constraints)
                    rs_target = get_rise_set_target(target)
                    airmasses = calculate_airmass_at_times(
                        night_times, rs_target, site_lat, site_lon, site_alt
                    )
                    if 'airmasses' in data['airmass_data'][site_id]:
                        for index, airmass_value in enumerate(airmasses):
                            data['airmass_data'][site_id]['airmasses'][index] += airmass_value
                    else:
                        data['airmass_data'][site_id]['airmasses'] = airmasses
                    max_airmass += constraints['max_airmass']
                # Now we need to divide out the number of unique constraints/targets
                data['airmass_limit'] = max_airmass / unique_count
                data['airmass_data'][site_id]['airmasses'] = [val / unique_count for val in data['airmass_data'][site_id]['airmasses']]

    return data


def exposure_completion_percentage(configuration_statuses):
    total_time = 0
    completed_time = 0
    for configuration_status in configuration_statuses:
        is_repeat_type = (
                'REPEAT' in configuration_status.configuration.type and
                configuration_status.configuration.repeat_duration is not None
        )
        has_summary = hasattr(configuration_status, 'summary')
        if is_repeat_type:
            if has_summary:
                completed_time += (
                    configuration_status.summary.end - configuration_status.summary.start
                ).total_seconds()
            total_time += configuration_status.configuration.repeat_duration
        else:
            if has_summary:
                completed_time += configuration_status.summary.time_completed
            for instrument_config in configuration_status.configuration.instrument_configs.all():
                total_time += instrument_config.exposure_count * instrument_config.exposure_time

    if float(total_time) == 0:
        return 100.0

    return (completed_time / total_time) * 100.0


def return_paginated_results(collection, url):
    response = requests.get(url)
    response.raise_for_status()
    collection += response.json()['results']
    if not response.json()['next']:
        return collection
    else:
        return return_paginated_results(collection, response.json()['next'])
