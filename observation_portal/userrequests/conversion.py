import os
import copy
import requests

VALHALLA_API_TOKEN = os.getenv('VALHALLA_API_TOKEN', '')
VALHALLA_URL = os.getenv('VALHALLA_URL', 'http://valhalladev.lco.gtn/api/userrequests/')
if not VALHALLA_URL.endswith('/'):
    VALHALLA_URL += '/'
VALHALLA_HEADERS = {'Authorization': 'Token ' + str(VALHALLA_API_TOKEN)}
VALIDATION_PROPOSAL = os.getenv('VALHALLA_VALIDATE_PROPOSAL', 'LCOSchedulerTest')


def validate_userrequest(userrequests):
    """
        Call a valhalla instance validate endpoint with the userrequest dict. Raise an error with the error response
        if it fails validation, otherwise return True
    :param userrequest_dict:
    :return: dictionary of validation errors
    """
    try:
        ur_copy = copy.deepcopy(userrequests)
        if isinstance(ur_copy, list):
            for ur in ur_copy:
                ur['proposal'] = VALIDATION_PROPOSAL
        else:
            ur_copy['proposal'] = VALIDATION_PROPOSAL
        response = requests.post(VALHALLA_URL + 'validate/', json=ur_copy, headers=VALHALLA_HEADERS)
        response.raise_for_status()
        body = response.json()
    except Exception as e:
        body = {'request_durations': {}, 'errors': 'Problem validating with old observation portal: {}'.format(repr(e))}
    return body


def expand_cadence(userrequest):
    """
        Call a valhalla instance to expand a cadence userrequest into a set of requests, which can then be submitted
        to the observation portal and converted into a requestgroup
    :param userrequest:
    :return: expanded userrequests
    """
    try:
        ur_copy = copy.deepcopy(userrequest)
        ur_copy['proposal'] = VALIDATION_PROPOSAL
        response = requests.post(VALHALLA_URL + 'cadence/', json=ur_copy, headers=VALHALLA_HEADERS)
        response.raise_for_status()
        body = response.json()
    except Exception as e:
        body = {'errors': 'Problem validating with old observation portal: {}'.format(repr(e))}
    return body


def convert_userrequests_to_requestgroups(userrequests):
    if isinstance(userrequests, list):
        return [convert_userrequest_to_requestgroup(ur) for ur in userrequests]
    else:
        return convert_userrequest_to_requestgroup(userrequests)


def convert_userrequest_to_requestgroup(userrequest):
    requestgroup = userrequest
    requestgroup['name'] = userrequest['group_id']
    del requestgroup['group_id']
    for request in requestgroup['requests']:
        target = request['target']
        constraints = request['constraints']
        configurations = []
        if 'observatory' in request['location']:
            request['location']['enclosure'] = request['location']['observatory']
            del request['location']['observatory']

        for molecule in request['molecules']:
            conf_extra_params = {}
            if molecule.get('args', ''):
                conf_extra_params['script_name'] = molecule['args']
            if molecule.get('ag_name') == molecule.get('instrument_name'):
                conf_extra_params['self_guiding'] = True

            optical_elements = {}
            if molecule.get('filter', ''):
                optical_elements['filter'] = molecule['filter']
            if molecule.get('spectra_slit', ''):
                if (molecule.get('type', '') != 'AUTO_FOCUS' or
                        molecule.get('instrument_name', '').upper() in ['2M0-FLOYDS-SCICAM', '1M0-NRES-SCICAM', '1M0-NRES-COMMISSIONING']):
                    optical_elements['slit'] = molecule['spectra_slit']
            if molecule.get('spectra_lamp', ''):
                optical_elements['lamp'] = molecule['spectra_lamp']

            inst_config_extra_params = {}
            if molecule.get('defocus', 0):
                inst_config_extra_params['defocus'] = molecule['defocus']
            if not molecule.get('expmeter_mode', 'OFF') == 'OFF':
                inst_config_extra_params['expmeter_mode'] = molecule['expmeter_mode']
                if molecule.get('expmeter_snr', None):
                    inst_config_extra_params['expmeter_snr'] = molecule['expmeter_snr']
            if target.get('rot_mode', '') == 'SKY':
                inst_config_extra_params['rotator_angle'] = target.get('rot_angle', 0.0)

            instrument_config = {
                'mode': molecule.get('readout_mode', ''),
                'exposure_time': molecule.get('exposure_time', 0.0),
                'exposure_count': molecule['exposure_count'],
                'rotator_mode': target.get('rot_mode', ''),
                'extra_params': inst_config_extra_params,
                'optical_elements': optical_elements
            }

            if 'bin_x' in molecule:
                instrument_config['bin_x'] = molecule['bin_x']
            if 'bin_y' in molecule:
                instrument_config['bin_y'] = molecule['bin_y']

            if molecule.get('sub_x1', 0) or molecule.get('sub_x2', 0) or molecule.get('sub_y1', 0) or molecule.get('sub_y2', 0):
                rois = [
                    {
                        'x1': molecule.get('sub_x1', 0),
                        'y1': molecule.get('sub_y1', 0),
                        'x2': molecule.get('sub_x2', 0),
                        'y2': molecule.get('sub_y2', 0)
                    }
                ]
                instrument_config['rois'] = rois

            ag_optical_elements = {}
            if molecule.get('ag_filter', ''):
                ag_optical_elements['filter'] = molecule['ag_filter']

            ag_extra_params = {}
            ag_mode = molecule.get('ag_mode', 'OFF')
            if ag_mode == 'OPTIONAL':
                ag_extra_params['optional'] = True
            elif ag_mode == 'ON':
                if molecule.get('ag_strategy', ''):
                    ag_mode = molecule['ag_strategy']

            guiding_config = {
                'optical_elements': ag_optical_elements,
                'mode': ag_mode,
                'extra_params': ag_extra_params
            }

            if 'ag_exp_time' in molecule:
                guiding_config['exposure_time'] = molecule['ag_exp_time']

            acquire_extra_params = {}
            if molecule.get('acquire_strategy', ''):
                acquire_extra_params['strategy'] = molecule['acquire_strategy']
            if molecule.get('acquire_mode', '') == 'BRIGHTEST':
                acquire_extra_params['acquire_radius'] = molecule['acquire_radius_arcsec']

            acquisition_config = {
                'mode': molecule.get('acquire_mode', 'OFF'),
                'extra_params': acquire_extra_params
            }

            if molecule.get('acquire_exp_time', None):
                acquisition_config['exposure_time'] = molecule['acquire_exp_time']

            configuration = {
                'type': molecule['type'],
                'instrument_type': molecule['instrument_name'],
                'extra_params': conf_extra_params,
                'target': target,
                'constraints': constraints,
                'instrument_configs': [instrument_config],
                'guiding_config': guiding_config,
                'acquisition_config': acquisition_config
            }
            if 'priority' in molecule:
                configuration['priority'] = molecule['priority']

            configurations.append(configuration)
        request['configurations'] = configurations
        del request['molecules']

    return requestgroup


def convert_requestgroups_to_userrequests(requestgroups):
    if isinstance(requestgroups, list):
        return [convert_requestgroup_to_userrequest(rg) for rg in requestgroups]
    else:
        return convert_requestgroup_to_userrequest(requestgroups)


def convert_requestgroup_to_userrequest(requestgroup):
    userrequest = requestgroup
    userrequest['group_id'] = requestgroup['name']
    del userrequest['name']
    for request in userrequest['requests']:
        request['completed'] = None  # if request['state'] != 'COMPLETED' else request['modified']
        request['target'] = request['configurations'][0]['target']
        request['target']['radvel'] = request['target'].get('extra_params', {}).get('radial_velocity', 0.0)
        request['target']['vmag'] = request['target'].get('extra_params', {}).get('v_magnitude', None)
        request['constraints'] = request['configurations'][0]['constraints']
        if 'enclosure' in request['location']:
            request['location']['observatory'] = request['location']['enclosure']
            del request['location']['enclosure']
        molecules = []
        for configuration in request['configurations']:
            first_inst_config = configuration['instrument_configs'][0]
            request['target']['rot_mode'] = first_inst_config.get('rotator_mode', '')
            request['target']['rot_angle'] = first_inst_config['extra_params'].get('rotator_angle', 0.0)

            ag_mode = configuration['guiding_config']['mode']
            if ag_mode not in ['OFF', 'ON']:
                ag_mode = 'ON'
            if configuration['guiding_config']['extra_params'].get('optional', False):
                ag_mode = 'OPTIONAL'

            molecule = {
                'type': configuration['type'],
                'instrument_name': configuration['instrument_type'],
                'priority': configuration['priority'],
                'args': configuration['extra_params'].get('script_name', ''),
                'ag_name': configuration['instrument_type'] if configuration['extra_params'].get('self_guiding', False) else '',
                'ag_mode': ag_mode,
                'ag_filter': configuration['guiding_config']['optical_elements'].get('filter', ''),
                'ag_strategy': configuration['guiding_config']['mode'],
                'filter': first_inst_config['optical_elements'].get('filter', ''),
                'readout_mode': first_inst_config['mode'],
                'spectra_lamp': first_inst_config['optical_elements'].get('lamp', ''),
                'spectra_slit': first_inst_config['optical_elements'].get('slit', ''),
                'acquire_mode': configuration['acquisition_config']['mode'],
                'acquire_radius_arcsec': configuration['acquisition_config']['extra_params'].get('radius', 0.0),
                'acquire_strategy': configuration['acquisition_config']['extra_params'].get('strategy', ''),
                'acquire_exp_time': configuration['acquisition_config'].get('exposure_time', None),
                'expmeter_mode': first_inst_config['extra_params'].get('expmeter_mode', 'OFF'),
                'expmeter_snr': first_inst_config['extra_params'].get('expmeter_snr', None),
                'exposure_time': first_inst_config['exposure_time'],
                'exposure_count': first_inst_config['exposure_count'],
                'bin_x': first_inst_config['bin_x'],
                'bin_y': first_inst_config['bin_y'],
                'defocus': first_inst_config['extra_params'].get('defocus', 0.0)
            }

            if 'exposure_time' in configuration['guiding_config']:
                molecule['ag_exp_time'] = configuration['guiding_config']['exposure_time']
            if 'rois' in first_inst_config and len(first_inst_config['rois']) > 0:
                molecule['sub_x1'] = first_inst_config['rois'][0]['x1']
                molecule['sub_y1'] = first_inst_config['rois'][0]['y1']
                molecule['sub_x2'] = first_inst_config['rois'][0]['x2']
                molecule['sub_y2'] = first_inst_config['rois'][0]['y2']

            molecules.append(molecule)
        request['molecules'] = molecules
        del request['configurations']

    return userrequest
