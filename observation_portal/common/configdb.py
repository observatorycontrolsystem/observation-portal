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


class TelescopeKey(namedtuple('TelescopeKey', ['site', 'observatory', 'telescope'])):
    __slots__ = ()

    def __str__(self):
        return ".".join(s for s in [self.site, self.observatory, self.telescope] if s)


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
                                                    observatory_code='', telescope_code=''):
        telescope_details = self.get_telescopes_with_instrument_type_and_location(instrument_type, site_code,
                                                                                  observatory_code, telescope_code)
        site_details = {}
        for code in telescope_details.keys():
            site = code.split('.')[2]
            if site not in site_details:
                site_details[site] = telescope_details[code]

        return site_details

    def get_telescopes_with_instrument_type_and_location(self, instrument_type='', site_code='',
                                                    observatory_code='', telescope_code=''):
        site_data = self.get_site_data()
        telescope_details = {}
        for site in site_data:
            if not site_code or site_code == site['code']:
                for enclosure in site['enclosure_set']:
                    if not observatory_code or observatory_code == enclosure['code']:
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
                                observatory=enclosure['code'],
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

    def get_optical_elements(self, instrument_type):
        '''
        Function returns the optical elements available for the instrument type specified using configd
        :param instrument_type:
        :return:
        '''
        optical_elements = {}
        for instrument in self.get_instruments(only_schedulable=True):
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                for optical_element_group in instrument['science_camera']['optical_element_groups']:
                    optical_elements[optical_element_group['type']] = []
                    for element in optical_element_group['optical_elements']:
                        optical_elements[optical_element_group['type']].append(element)

        return optical_elements

    def get_modes(self, instrument_type, mode_type=''):
        '''
            Function returns the set of available modes of different types for the instrument_type specified
        :param instrument_type:
        :return:
        '''
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                if not mode_type:
                    return instrument['science_camera']['camera_type']['modes']
                else:
                    for type, mode_details in instrument['science_camera']['camera_type']['modes'].items():
                        if type == mode_type:
                            return {type: mode_details}
        return {}

    def get_mode_with_code(self, instrument_type, code, mode_type=''):
        modes = self.get_modes(instrument_type, mode_type)
        for mode in modes:
            if mode['code'].lower() == code.lower():
                return mode

        raise ConfigDBException("No mode named {} found for instrument type {}".format(code, instrument_type))

    def get_readout_mode_with_binning(self, instrument_type, binning):
        readout_modes = self.get_modes(instrument_type, 'readout')
        readout_modes.sort(key=lambda x: x['default'], reverse=True)  # Start with the default
        for readout_mode in readout_modes:
            if readout_mode['params']['binning'] == binning:
                return readout_mode

        raise ConfigDBException("No readout mode found with binning {} for instrument type {}".format(binning,
                                                                                                      instrument_type))

    def get_default_modes(self, instrument_type, mode_type=''):
        '''
            Function returns the default mode of each available mode_type (or the specified mode_type) for the given
            instrument_type
        :param instrument_type:
        :param mode_type:
        :return:
        '''
        modes = self.get_modes(instrument_type, mode_type)
        for type, mode_set in modes.items():
            for mode in mode_set:
                if mode['default']:
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
        readout_modes = self.get_modes(instrument_type, 'readout')
        for mode in readout_modes['readout'] if 'readout' in readout_modes else []:
            if 'binning' in mode['params']:
                available_binnings.add(mode['params']['binning'])

        return available_binnings

    def get_default_binning(self, instrument_type):
        '''
            Function returns the default binning for the instrument type specified
        :param instrument_type:
        :return: binning default
        '''
        readout_modes = self.get_modes(instrument_type, 'readout')
        for mode in readout_modes['readout'] if 'readout' in readout_modes else []:
            if mode['default'] and 'binning' in mode['params']:
                return mode['params']['binning']
        return None

    def get_instrument_name(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['science_camera']['camera_type']['name']
        return instrument_type

    def get_active_instrument_types(self, location):
        '''
            Function uses the configdb to get a set of the available instrument_types.
            Location should be a dictionary of the location, with class, site, observatory, and telescope fields
        :return: Set of available instrument_types (i.e. 1M0-SCICAM-SBIG, etc.)
        '''
        instrument_types = set()
        for instrument in self.get_instruments(only_schedulable=True):
            split_string = instrument['__str__'].lower().split('.')
            if (location.get('site', '').lower() in split_string[0]
                    and location.get('observatory', '').lower() in split_string[1]
                    and location.get('telescope_class', '').lower() in split_string[2]
                    and location.get('telescope', '').lower() in split_string[2]):
                instrument_types.add(instrument['science_camera']['camera_type']['code'].upper())
        return instrument_types

    def get_exposure_overhead(self, instrument_type, binning, readout_mode=''):
        # using the instrument type, build an instrument with the correct configdb parameters
        for instrument in self.get_instruments():
            camera_type = instrument['science_camera']['camera_type']
            if camera_type['code'].upper() == instrument_type.upper():
                # get the binnings and put them into a dictionary
                default_mode = {}
                for mode in camera_type['modes']['readout'] if 'readout' in camera_type['modes'] else []:
                    if mode['default']:
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
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        camera_type = instrument['science_camera']['camera_type']
                        if camera_type['code'].upper() == instrument_type.upper():
                            return {'instrument_change_overhead': telescope['instrument_change_overhead'],
                                    'slew_rate': telescope['slew_rate'],
                                    'minimum_slew_overhead': telescope['minimum_slew_overhead'],
                                    'acquisition_overheads': {am['code']: am['overhead'] for am in camera_type['modes']['acquisition']} if 'acquisition' in camera_type['modes'] else {},
                                    'guiding_overheads': {gm['code']: gm['overhead'] for gm in camera_type['modes']['guiding']} if 'guiding' in camera_type['modes'] else {},
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
