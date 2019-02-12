import requests
from django.core.cache import caches
from django.utils.translation import ugettext as _
from django.conf import settings
from collections import namedtuple
import logging

logger = logging.getLogger(__name__)

CONFIGDB_ERROR_MSG = _(("ConfigDB connection is currently down, please wait a few minutes and try again."
                       " If this problem persists then please contact support."))


class ConfigDBException(Exception):
    pass


class TelescopeKey(namedtuple('TelescopeKey', ['site', 'enclosure', 'telescope'])):
    __slots__ = ()

    def __str__(self):
        return ".".join(s for s in [self.site, self.enclosure, self.telescope] if s)


class ConfigDB(object):
    def _get_configdb_data(self, resource):
        ''' Gets all the data from configdb (the sites structure with everything in it)
        :return: list of dictionaries of site data
        '''

        data = caches['locmem'].get(resource)
        if not data:
            try:
                r = requests.get(settings.CONFIGDB_URL + '/{}/'.format(resource))
                r.raise_for_status()
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                msg = "{}: {}".format(e.__class__.__name__, CONFIGDB_ERROR_MSG)
                raise ConfigDBException(msg)
            try:
                data = r.json()['results']
            except KeyError:
                raise ConfigDBException(CONFIGDB_ERROR_MSG)
            # cache the results for 15 minutes
            caches['locmem'].set(resource, data, 900)

        return data

    def get_site_data(self):
        return self._get_configdb_data('sites')

    def get_sites_with_instrument_type_and_location(self, instrument_type='', site_code='',
                                                    enclosure_code='', telescope_code=''):
        telescope_details = self.get_telescopes_with_instrument_type_and_location(instrument_type, site_code,
                                                                                  enclosure_code, telescope_code)
        site_details = {}
        for code in telescope_details.keys():
            site = code.split('.')[2]
            if site not in site_details:
                site_details[site] = telescope_details[code]

        return site_details

    def get_site_tuples(self, include_blank=False):
        site_data = self.get_site_data()
        sites = [(site['code'], site['code']) for site in site_data]
        if include_blank:
            sites.append(('', ''))
        return sites

    def get_enclosure_tuples(self, include_blank=False):
        enclosure_set = set()
        site_data = self.get_site_data()
        for site in site_data:
            for enclosure in site['enclosure_set']:
                enclosure_set.add(enclosure['code'])

        enclosures = [(enclosure, enclosure) for enclosure in enclosure_set]
        if include_blank:
            enclosures.append(('', ''))
        return enclosures

    def get_telescope_tuples(self, include_blank=False):
        telescope_set = set()
        site_data = self.get_site_data()
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    telescope_set.add(telescope['code'])

        telescopes = [(telescope, telescope) for telescope in telescope_set]
        if include_blank:
            telescopes.append(('', ''))
        return telescopes

    def get_telescope_class_tuples(self):
        telescope_classes = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    telescope_classes.add(telescope['code'][:-1])
        return [(telescope_class, telescope_class) for telescope_class in telescope_classes]

    def get_instrument_type_tuples(self):
        instrument_types = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        instrument_types.add(instrument['science_camera']['camera_type']['code'].upper())
        return [(instrument_type, instrument_type) for instrument_type in instrument_types]

    def get_instruments_at_location(self, site_code, enclosure_code, telescope_code):
        instrument_names = set()
        instrument_types = set()
        for site in self.get_site_data():
            if site['code'].lower() == site_code.lower():
                for enclosure in site['enclosure_set']:
                    if enclosure['code'].lower() == enclosure_code:
                        for telescope in enclosure['telescope_set']:
                            if telescope['code'].lower() == telescope_code:
                                for instrument in telescope['instrument_set']:
                                    instrument_names.add(instrument['science_camera']['code'].lower())
                                    instrument_types.add(instrument['science_camera']['camera_type']['code'].lower())
        return {'names': instrument_names, 'types': instrument_types}

    def get_telescopes_with_instrument_type_and_location(self, instrument_type='', site_code='',
                                                    enclosure_code='', telescope_code=''):
        site_data = self.get_site_data()
        telescope_details = {}
        for site in site_data:
            if not site_code or site_code == site['code']:
                for enclosure in site['enclosure_set']:
                    if not enclosure_code or enclosure_code == enclosure['code']:
                        for telescope in enclosure['telescope_set']:
                            if not telescope_code or telescope_code == telescope['code']:
                                code = '.'.join([telescope['code'], enclosure['code'], site['code']])
                                for instrument in telescope['instrument_set']:
                                    if instrument['state'] == 'SCHEDULABLE':
                                        camera_type = instrument['science_camera']['camera_type']['code']
                                        if not instrument_type or instrument_type.upper() == camera_type.upper():
                                            if code not in telescope_details:
                                                telescope_details[code] = {
                                                    'latitude': telescope['lat'],
                                                    'longitude': telescope['long'],
                                                    'horizon': telescope['horizon'],
                                                    'altitude': site['elevation'],
                                                    'ha_limit_pos': telescope['ha_limit_pos'],
                                                    'ha_limit_neg': telescope['ha_limit_neg']
                                                }

        return telescope_details

    def is_valid_instrument_type(self, instrument_type):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                            return True
        return False

    def is_valid_instrument(self, instrument_name):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if instrument_name.upper() == instrument['science_camera']['code'].upper():
                            return True
        return False

    def get_instruments(self, only_schedulable=False):
        site_data = self.get_site_data()
        instruments = []
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if only_schedulable and instrument['state'] != 'SCHEDULABLE':
                            pass
                        else:
                            telescope_key = TelescopeKey(
                                site=site['code'],
                                enclosure=enclosure['code'],
                                telescope=telescope['code']
                            )
                            instrument['telescope_key'] = telescope_key
                            instruments.append(instrument)

        return instruments

    def get_instrument_types_per_telescope(self, only_schedulable=False):
        '''
        Function uses the configdb to get a set of available instrument types per telescope
        :return: set of available instrument types per TelescopeKey
        '''
        telescope_instrument_types = {}
        for instrument in self.get_instruments(only_schedulable=only_schedulable):
            if instrument['telescope_key'] not in telescope_instrument_types:
                telescope_instrument_types[instrument['telescope_key']] = []
            instrument_type = instrument['science_camera']['camera_type']['code'].upper()
            if instrument_type not in telescope_instrument_types[instrument['telescope_key']]:
                telescope_instrument_types[instrument['telescope_key']].append(instrument_type)

        return telescope_instrument_types

    def get_instrument_names(self, instrument_type, site_code, enclosure_code, telescope_code):
        '''
        Function uses the configdb to get a set of available instruments per telescope
        :return: set of available instrument types per TelescopeKey
        '''
        instrument_names = set()
        for instrument in self.get_instruments():
            if (instrument['telescope_key'].site == site_code
                    and instrument['telescope_key'].enclosure == enclosure_code
                    and instrument['telescope_key'].telescope == telescope_code
                    and instrument['science_camera']['camera_type']['code'] == instrument_type):
                instrument_names.add(instrument['science_camera']['code'].lower())
        return instrument_names

    def get_instrument_types_per_telescope_class(self, only_schedulable=False):
        '''
            Function returns a set of instrument types per class of telescope (1m0, 0m4)
        :param only_schedulable:
        :return:
        '''
        telescope_instrument_types = {}
        for instrument in self.get_instruments(only_schedulable=only_schedulable):
            tel_code = instrument['telescope_key'].telescope[:3]
            if tel_code not in telescope_instrument_types:
                telescope_instrument_types[tel_code] = set()
            telescope_instrument_types[tel_code].add(instrument['science_camera']['camera_type']['code'].upper())

        return telescope_instrument_types

    def get_telescopes_per_instrument_type(self, instrument_type, only_schedulable=False):
        '''
        Function returns a set of telescope keys that have an instrument of instrument_type
        associated with them
        '''
        instrument_telescopes = set()
        for instrument in self.get_instruments(only_schedulable=only_schedulable):
            if instrument['science_camera']['camera_type']['code'].upper() == instrument_type:
                instrument_telescopes.add(instrument['telescope_key'])
        return instrument_telescopes

    def get_configuration_types(self, instrument_type):
        configuration_types = set()
        for instrument in self.get_instruments():
            if (instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper() or
                    instrument_type.upper() == instrument['science_camera']['code'].upper()):
                configuration_types.update(instrument['science_camera']['camera_type']['configuration_types'])

        return configuration_types

    def get_optical_elements(self, instrument_type):
        '''
        Function returns the optical elements available for the instrument type specified using configdb
        :param instrument_type:
        :return:
        '''
        optical_elements = {}
        for instrument in self.get_instruments(only_schedulable=True):
            if (instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper() or
                    instrument_type.upper() == instrument['science_camera']['code'].upper()):
                for optical_element_group in instrument['science_camera']['optical_element_groups']:
                    optical_elements[optical_element_group['type']] = []
                    for element in optical_element_group['optical_elements']:
                        optical_elements[optical_element_group['type']].append(element)

        return optical_elements

    def get_modes_by_type(self, instrument_type, mode_type=''):
        '''
            Function returns the set of available modes of different types for the instrument_type specified
        :param instrument_type:
        :return:
        '''
        for instrument in self.get_instruments():
            if (instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper() or
                    instrument_type.upper() == instrument['science_camera']['code'].upper()):
                if not mode_type:
                    return {mode_group['type']: mode_group for mode_group in instrument['science_camera']['camera_type']['mode_types']}
                else:
                    for mode_group in instrument['science_camera']['camera_type']['mode_types']:
                        if mode_group['type'] == mode_type:
                            return {mode_type: mode_group}
        return {}

    def get_mode_with_code(self, instrument_type, code, mode_type=''):
        modes_by_type = self.get_modes_by_type(instrument_type, mode_type)
        for _, mode_group in modes_by_type.items():
            for mode in mode_group['modes']:
                if mode['code'].lower() == code.lower():
                    return mode

        raise ConfigDBException("No mode named {} found for instrument type {}".format(code, instrument_type))

    def get_readout_mode_with_binning(self, instrument_type, binning):
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        if readout_modes:
            modes = sorted(readout_modes['readout']['modes'], key=lambda x: x['code'] == readout_modes['readout']['default'], reverse=True)  # Start with the default
            for mode in modes:
                if mode['params'].get('binning', -1) == binning:
                    return mode

        raise ConfigDBException("No readout mode found with binning {} for instrument type {}".format(binning,
                                                                                                      instrument_type))

    def get_default_modes_by_type(self, instrument_type, mode_type=''):
        '''
            Function returns the default mode of each available mode_type (or the specified mode_type) for the given
            instrument_type
        :param instrument_type:
        :param mode_type:
        :return:
        '''
        modes = self.get_modes_by_type(instrument_type, mode_type)
        for type, mode_set in modes.items():
            for mode in mode_set['modes']:
                if mode['code'] == mode_set['default']:
                    modes[type] = mode
                    break

        return modes

    def get_binnings(self, instrument_type):
        '''
            Function creates a set of available binning modes for the instrument_type specified
        :param instrument_type:
        :return: returns the available set of binnings for an instrument_type
        '''
        available_binnings = set()
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        for mode in readout_modes['readout']['modes'] if 'readout' in readout_modes else []:
            if 'binning' in mode['params']:
                available_binnings.add(mode['params']['binning'])

        return available_binnings

    def get_default_binning(self, instrument_type):
        '''
            Function returns the default binning for the instrument type specified
        :param instrument_type:
        :return: binning default
        '''
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        for mode in readout_modes['readout']['modes'] if 'readout' in readout_modes else []:
            if readout_modes['readout']['default'] == mode['code'] and 'binning' in mode['params']:
                return mode['params']['binning']
        return None

    def get_default_acceptability_threshold(self, instrument_type):
        for instrument in self.get_instruments():
            if (instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper() or
                    instrument_type.upper() == instrument['science_camera']['code'].upper()):
                return instrument['science_camera']['camera_type']['default_acceptability_threshold']

    def get_instrument_name(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['science_camera']['camera_type']['name']
        return instrument_type

    def get_active_instrument_types(self, location):
        '''
            Function uses the configdb to get a set of the available instrument_types.
            Location should be a dictionary of the location, with class, site, enclosure, and telescope fields
        :return: Set of available instrument_types (i.e. 1M0-SCICAM-SBIG, etc.)
        '''
        instrument_types = set()
        for instrument in self.get_instruments(only_schedulable=True):
            split_string = instrument['__str__'].lower().split('.')
            if (location.get('site', '').lower() in split_string[0]
                    and location.get('enclosure', '').lower() in split_string[1]
                    and location.get('telescope_class', '').lower() in split_string[2]
                    and location.get('telescope', '').lower() in split_string[2]):
                instrument_types.add(instrument['science_camera']['camera_type']['code'].upper())
        return instrument_types

    def get_autoguiders_for_science_camera(self, instrument_name):
        instruments = self.get_instruments(only_schedulable=False)
        valid_autoguiders = {''}
        for instrument in instruments:
            if (instrument['science_camera']['code'].upper() == instrument_name.upper() or
                    instrument['science_camera']['camera_type']['code'].upper() == instrument_name.upper()):
                valid_autoguiders.add(instrument['science_camera']['code'].upper())
                valid_autoguiders.add(instrument['science_camera']['camera_type']['code'].upper())
                valid_autoguiders.add(instrument['autoguider_camera']['camera_type']['code'].upper())
                valid_autoguiders.add(instrument['autoguider_camera']['code'].upper())

        return valid_autoguiders

    def get_exposure_overhead(self, instrument_type, binning, readout_mode=''):
        # using the instrument type, build an instrument with the correct configdb parameters
        for instrument in self.get_instruments():
            if (instrument['science_camera']['camera_type']['code'].upper() == instrument_type.upper() or
                    instrument_type.upper() == instrument['science_camera']['code'].upper()):
                camera_type = instrument['science_camera']['camera_type']

        modes_by_type = self.get_modes_by_type(instrument_type, mode_type='readout')
        if 'readout' in modes_by_type:
            default_mode = {}
            for mode in modes_by_type['readout']['modes']:
                if mode['code'] == modes_by_type['readout']['default']:
                    default_mode = mode
                if readout_mode and readout_mode.lower() != mode['code'].lower():
                    continue
                if 'binning' in mode['params'] and mode['params']['binning'] == binning:
                    return mode['overhead'] + camera_type['fixed_overhead_per_exposure']
            # if the binning is not found, return the default binning (Added to support legacy 2x2 Sinistro obs)
            return default_mode['overhead'] + camera_type['fixed_overhead_per_exposure']

        raise ConfigDBException("Instrument type {} not found in configdb.".format(instrument_type))

    def get_request_overheads(self, instrument_type):
        '''
            Gets the set of overheads needed to compute the duration of an request using the instrument_type given.
            This assumes a fixed set of overheads per instrument_type, but we could in the future split these off
            further by specific telescopes, or by specific instruments.
        :param instrument_type:
        :return:
        '''
        site_data = self.get_site_data()
        modes_by_type = self.get_modes_by_type(instrument_type)
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        camera_type = instrument['science_camera']['camera_type']
                        if (camera_type['code'].upper() == instrument_type.upper() or
                                instrument['science_camera']['code'].upper() == instrument_type.upper()):
                            return {'instrument_change_overhead': telescope['instrument_change_overhead'],
                                    'slew_rate': telescope['slew_rate'],
                                    'minimum_slew_overhead': telescope['minimum_slew_overhead'],
                                    'maximum_slew_overhead': telescope.get('maximum_slew_overhead', 0.0),
                                    'config_change_overhead': camera_type['config_change_time'],
                                    'acquisition_overheads': {am['code']: am['overhead'] for am in modes_by_type['acquisition']['modes']} if 'acquisition' in modes_by_type else {},
                                    'guiding_overheads': {gm['code']: gm['overhead'] for gm in modes_by_type['guiding']['modes']} if 'guiding' in modes_by_type else {},
                                    'front_padding': camera_type['front_padding'],
                                    'optical_element_change_overheads':
                                        {oeg['type']: oeg['element_change_overhead'] for oeg in instrument['science_camera']['optical_element_groups']}
                                    }

        raise ConfigDBException("Instrument type {} not found in configdb.".format(instrument_type))

    @staticmethod
    def is_spectrograph(instrument_type):
        return instrument_type.upper() in ['2M0-FLOYDS-SCICAM', '0M8-NRES-SCICAM', '1M0-NRES-SCICAM',
                                           '1M0-NRES-COMMISSIONING']

    @staticmethod
    def is_nres(instrument_type):
        return 'NRES' in instrument_type.upper()

    @staticmethod
    def is_floyds(instrument_type):
        return 'FLOYDS' in instrument_type.upper()


configdb = ConfigDB()
