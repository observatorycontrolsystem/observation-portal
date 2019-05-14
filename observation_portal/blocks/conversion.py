import copy
from observation_portal.requestgroups.models import RequestGroup


POND_POINTING_TYPE_TO_TARGET_TYPE = {
    'SP': 'SIDEREAL',
    'NS': 'NON_SIDEREAL',
    'ST': 'SATELLITE',
}

TARGET_TYPE_TO_POND_POINTING_TYPE = {
    'SIDEREAL': 'SP',
    'NON_SIDEREAL': 'NS',
    'SATELLITE': 'ST',
    'STATIC': 'ST',
}

BLOCK_REQUIRED_FIELDS = ['instrument_class', 'site', 'observatory', 'telescope', 'start', 'end']
MOLECULE_REQUIRED_FIELDS = ['type', 'inst_name']


class PondBlockError(Exception):
    pass


def convert_pond_blocks_to_observations(blocks):
    if isinstance(blocks, list):
        return [convert_pond_block_to_observation(block) for block in blocks]
    else:
        return convert_pond_block_to_observation(blocks)


def convert_pond_block_to_observation(block):
    if not block.get('molecules', []):
        raise PondBlockError("blocks must contain at least one molecule")

    for field in BLOCK_REQUIRED_FIELDS:
        if field not in block:
            raise PondBlockError("Blocks must include {} field".format(field))

    first_molecule = block['molecules'][0]
    observation = {
        'site': block.get('site', ''),
        'enclosure': block.get('observatory', ''),
        'telescope': block.get('telescope', ''),
        'start': block.get('start', ''),
        'end': block.get('end', ''),
        'name': first_molecule.get('group', ''),
        'proposal': first_molecule.get('prop_id', '')
    }

    if first_molecule.get('user_id'):
        observation['submitter'] = first_molecule['user_id']

    if block.get('canceled'):
        observation['state'] = 'CANCELED'
    elif block.get('aborted'):
        observation['state'] = 'ABORTED'
    elif all([mol.get('completed') for mol in block['molecules']]):
        observation['state'] = 'COMPLETED'
    elif any([mol.get('failed') for mol in block['molecules']]):
        observation['state'] = 'FAILED'
    elif any([mol.get('attempted') for mol in block['molecules']]):
        observation['state'] = 'IN_PROGRESS'
    elif 'canceled' in block and 'aborted' in block:
        observation['state'] = 'PENDING'

    if first_molecule.get('tracking_num'):
        observation['request_group_id'] = int(first_molecule['tracking_num'])

    constraints = {
        'max_airmass': float(block.get('max_airmass', 1.6)),
        'min_lunar_distance': float(block.get('min_lunar_dist', 30.0)),
        'extra_params': {}
    }

    configurations = []
    for index, molecule in enumerate(block['molecules']):
        for field in MOLECULE_REQUIRED_FIELDS:
            if field not in molecule:
                raise PondBlockError("Molecules must include {} field".format(field))

        pointing = molecule.get('pointing', {})
        target = pointing_to_target(pointing)

        config_extra_params = {}
        if molecule.get('args'):
            config_extra_params['script_name'] = molecule['margs']
        if molecule.get('ag_name') and molecule.get('ag_name', '').upper() == molecule.get('inst_name', '').upper():
            config_extra_params['self_guiding'] = True

        instrument_extra_params = {}
        if 'rot_angle' in pointing and float(pointing['rot_angle']):
            instrument_extra_params['rotator_angle'] = float(pointing['rot_angle'])
        if 'defocus' in molecule and float(molecule['defocus']):
            instrument_extra_params['defocus'] = float(molecule['defocus'])
        if 'expmeter_mode' in molecule and not molecule['expmeter_mode'] in ['OFF', 'EXPMETER_OFF']:
            instrument_extra_params['expmeter_mode'] = molecule['expmeter_mode']
            if 'expmeter_snr' in molecule and float(molecule['expmeter_snr']):
                instrument_extra_params['expmeter_snr'] = float(molecule['expmeter_snr'])

        instrument_optical_elements = {}
        if molecule.get('filter'):
            instrument_optical_elements['filter'] = molecule['filter']
        if molecule.get('spectra_slit'):
            instrument_optical_elements['slit'] = molecule['spectra_slit']
        if molecule.get('spectra_lamp'):
            instrument_optical_elements['lamp'] = molecule['spectra_lamp']

        instrument_configs = [{
            'mode': molecule.get('readout_mode', ''),
            'rotator_mode': pointing.get('rot_mode', ''),
            'exposure_time': float(molecule.get('exposure_time', 0.01)),
            'exposure_count': molecule.get('exposure_count', 1),
            'bin_x': molecule.get('bin_x', 1),
            'bin_y': molecule.get('bin_y', 1),
            'optical_elements': instrument_optical_elements,
            'extra_params': instrument_extra_params
        }]

        if molecule.get('sub_x1') and molecule.get('sub_x2') and molecule.get('sub_y1') and molecule.get('sub_y2'):
            instrument_configs[0]['rois'] = [{'x1': float(molecule['sub_x1']),
                                              'x2': float(molecule['sub_x2']),
                                              'y1': float(molecule['sub_y1']),
                                              'y2': float(molecule['sub_y2'])}]

        ag_optical_elements = {}
        if molecule.get('ag_filter'):
            ag_optical_elements['filter'] = molecule['ag_filter']

        ag_extra_params = {}
        if molecule.get('ag_strategy'):
            ag_extra_params['strategy'] = molecule['ag_strategy']

        (guide_mode, guide_optional) = pond_ag_mode_to_guiding_mode(molecule.get('ag_mode', 'OPT'))

        guiding_config = {
            'mode': guide_mode,
            'optional': guide_optional,
            'exposure_time': float(molecule.get('ag_exp_time', 10)),
            'optical_elements': ag_optical_elements,
            'extra_params': ag_extra_params
        }

        acquire_mode = 'OFF'
        acquire_extra_params = {}
        if not molecule.get('acquire_mode', 'OFF') == 'OFF':
            acquire_mode = molecule['acquire_mode']
            if molecule.get('acquire_strategy'):
                acquire_extra_params['strategy'] = molecule['acquire_strategy']
            if molecule['acquire_mode'] == 'BRIGHTEST' and molecule.get('acquire_radius_arcsec'):
                acquire_extra_params['acquire_radius'] = float(molecule['acquire_radius_arcsec'])

        acquisition_config = {
            'mode': acquire_mode,
            'extra_params': acquire_extra_params
        }

        if float(molecule.get('acquire_exp_time', 0)):
            acquisition_config['exposure_time'] = float(molecule['acquire_exp_time'])

        configuration = {
            'priority': molecule.get('priority', index),
            'instrument_type': block['instrument_class'],
            'instrument_name': molecule['inst_name'],
            'type': molecule['type'],
            'instrument_configs': instrument_configs,
            'acquisition_config': acquisition_config,
            'guiding_config': guiding_config,
            'constraints': constraints,
            'target': target,
            'extra_params': config_extra_params
        }

        if molecule.get('completed'):
            configuration['state'] = 'COMPLETED'
        elif molecule.get('failed'):
            configuration['state'] = 'FAILED'
        elif 'attempted' in molecule:
            configuration['state'] = 'ATTEMPTED' if molecule['attempted'] else 'PENDING'

        if molecule.get('ag_name'):
            configuration['guide_camera_name'] = molecule['ag_name']

        configurations.append(configuration)

    request = {
        'configurations': configurations
    }

    observation['request'] = request

    return observation


def pond_ag_mode_to_guiding_mode(mode):
    return {
        'YES': ('ON', False),
        'NO': ('OFF', False),
        'OPT': ('ON', True)
    }[mode]


def pointing_to_target(pointing):
    ttype = POND_POINTING_TYPE_TO_TARGET_TYPE[pointing.get('type', 'SP')]
    target = {
        'coordinate_system': pointing.get('coord_sys', ''),
        'name': pointing.get('name', 'my target'),
        'type': ttype
    }
    if ttype == 'SIDEREAL':
        if pointing.get('coord_type', 'RD') == 'RD':
            if 'epoch' in pointing:
                target['epoch'] = float(pointing['epoch'])
            if 'equinox' in pointing:
                target['equinox'] = pointing['equinox']
            if 'parallax' in pointing and float(pointing['parallax']):
                target['parallax'] = float(pointing['parallax'])
            if 'pro_mot_ra' in pointing and float(pointing['pro_mot_ra']):
                target['proper_motion_ra'] = float(pointing['pro_mot_ra'])
            if 'pro_mot_dec' in pointing and float(pointing['pro_mot_dec']):
                target['proper_motion_dec'] = float(pointing['pro_mot_dec'])
            if 'ra' in pointing:
                target['ra'] = float(pointing['ra'])
            if 'dec' in pointing:
                target['dec'] = float(pointing['dec'])
        elif pointing.get('coord_type') == 'HD':
            if 'ha' in pointing:
                target['hour_angle'] = float(pointing['ha'])
            if 'dec' in pointing:
                target['dec'] = float(pointing['dec'])
        else:
            raise PondBlockError("Only Coordinate Types RD and HD are supported in the shim")
    elif ttype == 'NON_SIDEREAL':
        if 'scheme' in pointing:
            target['scheme'] = pointing['scheme']
        if 'epochofel' in pointing and float(pointing['epochofel']):
            target['epochofel'] = float(pointing['epochofel'])
        if 'orbinc' in pointing and float(pointing['orbinc']):
            target['orbinc'] = float(pointing['orbinc'])
        if 'longascnode' in pointing and float(pointing['longascnode']):
            target['longascnode'] = float(pointing['longascnode'])
        if 'longofperih' in pointing and float(pointing['longofperih']):
            target['longofperih'] = float(pointing['longofperih'])
        if 'meandist' in pointing and float(pointing['meandist']):
            target['meandist'] = float(pointing['meandist'])
        if 'eccentricity' in pointing and float(pointing['eccentricity']):
            target['eccentricity'] = float(pointing['eccentricity'])
        if 'argofperih' in pointing and float(pointing['argofperih']):
            target['argofperih'] = float(pointing['argofperih'])
        if 'meananom' in pointing and float(pointing['meananom']):
            target['meananom'] = float(pointing['meananom'])
        if 'epochofperih' in pointing and float(pointing['epochofperih']):
            target['epochofperih'] = float(pointing['epochofperih'])
        if 'perihdist' in pointing and float(pointing['perihdist']):
            target['perihdist'] = float(pointing['perihdist'])
        if 'dailymot' in pointing and float(pointing['dailymot']):
            target['dailymot'] = float(pointing['dailymot'])
    else:
        # Static or Satellite type
        if pointing.get('coord_type', 'RD') == 'RD':
            if 'ra' in pointing:
                target['ra'] = float(pointing['ra'])
            if 'dec' in pointing:
                target['dec'] = float(pointing['dec'])
            if 'diff_epoch_rate' in pointing and float(pointing['diff_epoch_rate']):
                target['diff_epoch_rate'] = float(pointing['diff_epoch_rate'])
            if 'diff_ra_rate' in pointing and float(pointing['diff_ra_rate']):
                target['diff_roll_rate'] = float(pointing['diff_ra_rate'])
            if 'diff_dec_rate' in pointing and float(pointing['diff_dec_rate']):
                target['diff_pitch_rate'] = float(pointing['diff_dec_rate'])
            if 'diff_ra_accel' in pointing and float(pointing['diff_ra_accel']):
                target['diff_roll_acceleration'] = float(pointing['diff_ra_accel'])
            if 'diff_dec_accel' in pointing and float(pointing['diff_dec_accel']):
                target['diff_pitch_acceleration'] = float(pointing['diff_dec_accel'])
        elif pointing.get('coord_type') == 'HD':
            if 'ha' in pointing:
                target['hour_angle'] = float(pointing['ha'])
            if 'dec' in pointing:
                target['dec'] = float(pointing['dec'])
        else:
            raise PondBlockError("Only Coordinate Types RD and HD are supported in the shim")

    extra_params = {}
    if 'vmag' in pointing and float(pointing['vmag']):
        extra_params['v_magnitude'] = float(pointing['vmag'])
    if 'radvel' in pointing and float(pointing['radvel']):
        extra_params['radial_velocity'] = float(pointing['radvel'])
    target['extra_params'] = extra_params

    return target


def convert_observations_to_pond_blocks(observations):
    if isinstance(observations, list):
        return [convert_observation_to_pond_block(obs) for obs in observations]
    else:
        return convert_observation_to_pond_block(observations)


def convert_observation_to_pond_block(observation):
    first_configuration = observation['request']['configurations'][0]

    block = {
        'start': observation['start'],
        'end': observation['end'],
        'id': observation['id'],
        'site': observation['site'],
        'observatory': observation['enclosure'],
        'telescope': observation['telescope'],
        'instrument_class': first_configuration['instrument_type'],
        'max_airmass': str(first_configuration['constraints']['max_airmass']),
        'min_lunar_dist': str(first_configuration['constraints']['min_lunar_distance']),
        'is_too': observation['observation_type'] == RequestGroup.RAPID_RESPONSE,
        'canceled': observation['state'] == 'CANCELED',
        'cancel_reason': '',
        'cancel_date': '',
        'aborted': observation['state'] == 'ABORTED'
    }

    if (block['canceled'] or block['aborted']) and 'modified' in observation:
        block['cancel_date'] = min(observation['modified'], block['end'])

    if first_configuration['extra_params'].get('script_name'):
        block['script_name'] = first_configuration['extra_params']['script_name']

    molecules = []
    for index, configuration in enumerate(observation['request']['configurations']):
        pointing = configuration_to_pointing(configuration)
        first_instrument_config = configuration['instrument_configs'][0]
        optical_elements = first_instrument_config['optical_elements']
        ag_mode = 'OFF' if configuration['guiding_config']['mode'] == 'OFF' else 'ON'
        if configuration['guiding_config']['optional']:
            ag_mode = 'OPT'

        events = []
        if configuration.get('summary'):
            events.append(copy.deepcopy(configuration['summary']))
            completed_exposures = events[0].get('time_completed', 0) // first_instrument_config.get('exposure_time', 1)
            events[0]['completed_exposures'] = completed_exposures
            del events[0]['time_completed']
            del events[0]['events']
            if 'configuration_status' in events[0]:
                del events[0]['configuration_status']
            if 'id' in events[0]:
                del events[0]['id']

        molecule = {
            'pointing': pointing,
            'inst_name': configuration['instrument_name'],
            'ag_name': configuration['guide_camera_name'],
            'id': configuration['configuration_status'],
            'request_num': str(observation['request']['id']).zfill(10),
            'tracking_num': str(observation['request_group_id']).zfill(10),
            'user_id': observation['submitter'],
            'prop_id': observation['proposal'],
            'group': observation['name'],
            'exposure_count': first_instrument_config['exposure_count'],
            'exposure_time': str(first_instrument_config['exposure_time']),
            'bin_x': first_instrument_config['bin_x'],
            'bin_y': first_instrument_config['bin_y'],
            'readout_mode': first_instrument_config['mode'],
            'type': configuration['type'],
            'completed': configuration['state'] == 'COMPLETED',
            'attempted': configuration['state'] != 'PENDING',
            'failed': configuration['state'] == 'FAILED',
            'ag_exp_time': str(configuration['guiding_config']['exposure_time']),
            'ag_mode': ag_mode,
            'priority': index + 1,
            'events': events
        }

        if observation['request'].get('observation_note'):
            molecule['obs_note'] = observation['request']['observation_note']
        if configuration['acquisition_config']['mode'] != 'OFF':
            molecule['acquire_mode'] = configuration['acquisition_config']['mode']
        if configuration['acquisition_config']['extra_params'].get('strategy'):
            molecule['acquire_strategy'] = configuration['acquisition_config']['extra_params']['strategy']
        if configuration['acquisition_config']['extra_params'].get('acquire_radius'):
            molecule['acquire_radius_arcsec'] = str(configuration['acquisition_config']['extra_params']['acquire_radius'])
        if first_instrument_config['extra_params'].get('expmeter_mode'):
            molecule['expmeter_mode'] = first_instrument_config['extra_params']['expmeter_mode']
        if first_instrument_config['extra_params'].get('expmeter_snr'):
            molecule['expmeter_snr'] = str(first_instrument_config['extra_params']['expmeter_snr'])
        if first_instrument_config.get('rois', []):
            first_roi = first_instrument_config['rois'][0]
            molecule['sub_x1'] = first_roi['x1']
            molecule['sub_x2'] = first_roi['x2']
            molecule['sub_y1'] = first_roi['y1']
            molecule['sub_y2'] = first_roi['y2']
        if configuration['extra_params'].get('script_name'):
            molecule['args'] = configuration['extra_params']['script_name']
        if first_instrument_config['extra_params'].get('defocus'):
            molecule['defocus'] = str(first_instrument_config['extra_params']['defocus'])
        if configuration['guiding_config']['extra_params'].get('strategy'):
            molecule['ag_strategy'] = configuration['guiding_config']['extra_params']['strategy']
        if 'filter' in optical_elements:
            molecule['filter'] = optical_elements['filter']
        if 'slit' in optical_elements:
            molecule['spectra_slit'] = optical_elements['slit']
        if 'lamp' in optical_elements:
            molecule['spectra_lamp'] = optical_elements['lamp']
        if 'filter' in configuration['guiding_config']['optical_elements']:
            molecule['ag_filter'] = configuration['guiding_config']['optical_elements']['filter']
        if configuration['acquisition_config'].get('exposure_time'):
            molecule['acquire_exp_time'] = str(configuration['acquisition_config']['exposure_time'])

        molecules.append(molecule)

    block['molecules'] = molecules

    return block


def configuration_to_pointing(configuration):
    target = configuration['target']
    pointing = copy.deepcopy(target)
    for field in pointing:
        if isinstance(pointing[field], float):
            pointing[field] = str(pointing[field])

    pointing['type'] = TARGET_TYPE_TO_POND_POINTING_TYPE[target['type']]

    if 'proper_motion_ra' in pointing:
        pointing['pro_mot_ra'] = pointing['proper_motion_ra']
        del pointing['proper_motion_ra']
    if 'proper_motion_dec' in pointing:
        pointing['pro_mot_dec'] = pointing['proper_motion_dec']
        del pointing['proper_motion_dec']

    roll_converter = 'roll'
    pitch_converter = 'pitch'

    if 'ra' in pointing:
        pointing['coord_type'] = 'RD'
        roll_converter = 'ra'
        pitch_converter = 'dec'
    elif 'altitude' in pointing and 'azimuth' in pointing:
        pointing['coord_type'] = 'AA'
        pointing['alt'] = pointing['altitude']
        del pointing['altitude']
        pointing['az'] = pointing['azimuth']
        del pointing['azimuth']
        roll_converter = 'az'
        pitch_converter = 'alt'
    elif 'hour_angle' in pointing:
        pointing['coord_type'] = 'HD'
        pointing['ha'] = pointing['hour_angle']
        del pointing['hour_angle']
    elif 'pitch' in pointing and 'roll' in pointing:
        pointing['coord_type'] = 'PR'

    if 'diff_pitch_rate' in pointing and pitch_converter != 'pitch':
        pointing['diff_{}_rate'.format(pitch_converter)] = pointing['diff_pitch_rate']
        del pointing['diff_pitch_rate']
    if 'diff_pitch_acceleration' in pointing:
        pointing['diff_{}_accel'.format(pitch_converter)] = pointing['diff_pitch_acceleration']
        del pointing['diff_pitch_acceleration']
    if 'diff_roll_rate' in pointing and roll_converter != 'roll':
        pointing['diff_{}_rate'.format(roll_converter)] = pointing['diff_roll_rate']
        del pointing['diff_roll_rate']
    if 'diff_roll_acceleration' in pointing:
        pointing['diff_{}_accel'.format(roll_converter)] = pointing['diff_roll_acceleration']
        del pointing['diff_roll_acceleration']

    if 'extra_params' in pointing:
        if target.get('extra_params', {}).get('v_magnitude'):
            pointing['vmag'] = str(target['extra_params']['v_magnitude'])
        if target.get('extra_params', {}).get('radial_velocity'):
            pointing['radvel'] = str(target['extra_params']['radial_velocity'])
        del pointing['extra_params']

    if configuration['instrument_configs'][0]['extra_params'].get('rotator_angle'):
        pointing['rot_angle'] = configuration['instrument_configs'][0]['extra_params']['rotator_angle']
    pointing['rot_mode'] = configuration['instrument_configs'][0]['rotator_mode']

    return pointing