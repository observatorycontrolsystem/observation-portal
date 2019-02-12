from datetime import timedelta
from rise_set.angle import Angle
from rise_set.astrometry import calculate_airmass_at_times
import requests

from observation_portal.common.configdb import configdb
from observation_portal.common.telescope_states import TelescopeStates, filter_telescope_states_by_intervals
from observation_portal.common.rise_set_utils import get_rise_set_target, get_rise_set_intervals

# TODO: Use configuration types from configdb

MOLECULE_TYPE_DISPLAY = {
  'EXPOSE': 'Imaging',
  'SKY_FLAT': 'Sky Flat',
  'STANDARD': 'Standard',
  'ARC': 'Arc',
  'LAMP_FLAT': 'Lamp Flat',
  'SPECTRUM': 'Spectrum',
  'AUTO_FOCUS': 'Auto Focus',
  'TRIPLE': 'Triple',
  'NRES_TEST': 'NRES Test',
  'NRES_SPECTRUM': 'NRES Spectrum',
  'NRES_EXPOSE': 'NRES Expose',
  'ENGINEERING': 'Engineering',
  'SCRIPT': 'Script'
}


def get_telescope_states_for_request(request):
    # TODO: update to support multiple instruments in a list
    instrument_type = request.configurations.first().instrument_class
    site_intervals = {}
    # Build up the list of telescopes and their rise set intervals for the target on this request
    site_data = configdb.get_sites_with_instrument_type_and_location(
      instrument_type=instrument_type,
      site_code=request.location.site,
      observatory_code=request.location.observatory,
      telescope_code=request.location.telescope
    )
    for site, details in site_data.items():
        if site not in site_intervals:
            site_intervals[site] = get_rise_set_intervals(request.as_dict, site)
    # If you have no sites, return the empty dict here
    if not site_intervals:
        return {}

    # Retrieve the telescope states for that set of sites
    telescope_states = TelescopeStates(
      start=request.min_window_time,
      end=request.max_window_time,
      sites=list(site_intervals.keys()),
      instrument_types=[instrument_type]
    ).get()
    # Remove the empty intervals from the dictionary
    site_intervals = {site: intervals for site, intervals in site_intervals.items() if intervals}

    # Filter the telescope states list with the site intervals
    filtered_telescope_states = filter_telescope_states_by_intervals(
      telescope_states, site_intervals, request.min_window_time, request.max_window_time
    )

    return filtered_telescope_states


def date_range_from_interval(start_time, end_time, dt=timedelta(minutes=15)):
    time = start_time
    while time < end_time:
        yield time
        time += dt


def get_airmasses_for_request_at_sites(request_dict):
    # TODO: Change to work with multiple instrument types and multiple constraints and multiple targets
    instrument_type = request_dict['configurations'][0]['instrument_class']
    constraints = request_dict['configurations'][0]['constraints']

    site_data = configdb.get_sites_with_instrument_type_and_location(
      instrument_type=instrument_type,
      site_code=request_dict['location'].get('site'),
      observatory_code=request_dict['location'].get('observatory'),
      telescope_code=request_dict['location'].get('telescope')
    )

    rs_target = get_rise_set_target(request_dict['configurations'][0]['target'])

    data = {'airmass_data': {}}
    if request_dict['configurations'][0]['target']['type'].upper() != 'SATELLITE':
        for site_id, site_details in site_data.items():
            night_times = []
            site_lat = Angle(degrees=site_details['latitude'])
            site_lon = Angle(degrees=site_details['longitude'])
            site_alt = site_details['altitude']
            intervals = get_rise_set_intervals(request_dict, site_id)
            for interval in intervals:
                night_times.extend(
                    [time for time in date_range_from_interval(interval[0], interval[1], dt=timedelta(minutes=10))])

            if len(night_times) > 0:
                if site_id not in data:
                    data['airmass_data'][site_id] = {}
                data['airmass_data'][site_id]['times'] = [time.strftime('%Y-%m-%dT%H:%M') for time in night_times]
                data['airmass_data'][site_id]['airmasses'] = calculate_airmass_at_times(
                  night_times, rs_target, site_lat, site_lon, site_alt
                )
                data['airmass_limit'] = constraints['max_airmass']

    return data


def exposure_completion_percentage_from_pond_block(pond_block):
    total_exposure_time = 0
    completed_exposure_time = 0
    for molecule in pond_block['molecules']:
        event = molecule['events'][0] if molecule['events'] else {}
        exp_time = float(molecule['exposure_time'])
        exp_cnt = molecule['exposure_count']
        if molecule['completed']:
            completed_exp_cnt = exp_cnt
        elif 'completed_exposures' in event:
            completed_exp_cnt = event['completed_exposures']
        else:
            completed_exp_cnt = 0
        total_exposure_time += exp_time * exp_cnt
        completed_exposure_time += exp_time * completed_exp_cnt

    if float(total_exposure_time) == 0:
        return 100.0

    return (completed_exposure_time / total_exposure_time) * 100.0


def return_paginated_results(collection, url):
    response = requests.get(url)
    response.raise_for_status()
    collection += response.json()['results']
    if not response.json()['next']:
        return collection
    else:
        return return_paginated_results(collection, response.json()['next'])
