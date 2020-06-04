from django.utils.translation import ugettext as _
from numbers import Number


class BaseTargetHelper(object):
    """
    These helper classes take a dictionary representation of a target
    and performs validation specific to the target type ICRS, HourAngle,
    OribtalElements, Satellite. The dictionary it returns will also only contain
    fields relevant to the specific type. These models should only be used in
    TargetSerializer
    """
    def __init__(self, target):
        self.error_dict = {}
        self._data = {}

        for field in self.fields:
            self._data[field] = target.get(field)

        for field in self.defaults:
            if not target.get(field):
                self._data[field] = self.defaults[field]

        for field in self.required_fields:
            if not self._data.get(field) and not isinstance(self._data.get(field), Number):
                self.error_dict[field] = ['This field is required']

        self.validate()

    def validate(self):
        pass

    def is_valid(self):
        return not bool(self.error_dict)

    @property
    def data(self):
        # Only return data that is not none so model defaults can take effect
        return {k: v for k, v in self._data.items() if v is not None}


class ICRSTargetHelper(BaseTargetHelper):
    def __init__(self, target):
        self.fields = (
            'type', 'name', 'ra', 'dec', 'proper_motion_ra', 'proper_motion_dec', 'parallax',
            'epoch', 'hour_angle'
        )

        if target.get('type') == 'HOUR_ANGLE':
            self.required_fields = ('hour_angle', 'dec')
        else:
            self.required_fields = ('ra', 'dec')

        self.defaults = {
            'parallax': 0.0,
            'proper_motion_ra': 0.0,
            'proper_motion_dec': 0.0,
            'epoch': 2000.0
        }
        super().__init__(target)


class OrbitalElementsTargetHelper(BaseTargetHelper):
    def __init__(self, target):
        self.defaults = {}
        self.fields = ()
        self.required_fields = (
            'type', 'name', 'epochofel', 'orbinc', 'longascnode', 'eccentricity', 'scheme'
        )
        if target.get('scheme') == 'ASA_MAJOR_PLANET':
            self.required_fields += ('longofperih', 'meandist', 'meanlong', 'dailymot')
        elif target.get('scheme') == 'ASA_MINOR_PLANET':
            self.required_fields += ('argofperih', 'meandist', 'meananom')
        elif target.get('scheme') == 'ASA_COMET':
            self.required_fields += ('argofperih', 'perihdist', 'epochofperih')
        elif target.get('scheme') == 'JPL_MAJOR_PLANET':
            self.required_fields += ('argofperih', 'meandist', 'meananom', 'dailymot')
        elif target.get('scheme') == 'JPL_MINOR_PLANET':
            self.required_fields += ('argofperih', 'perihdist', 'epochofperih')
        elif target.get('scheme') == 'MPC_MINOR_PLANET':
            self.required_fields += ('argofperih', 'meandist', 'meananom')
        elif target.get('scheme') == 'MPC_COMET':
            self.required_fields += ('argofperih', 'perihdist', 'epochofperih')

        self.fields += self.required_fields
        super().__init__(target)

    def validate(self):
        ECCENTRICITY_LIMIT = 0.9
        if self.is_valid() and 'COMET' not in self._data['scheme'] and self._data['eccentricity'] > ECCENTRICITY_LIMIT:
            msg = _("ORBITAL_ELEMENTS pointing of scheme {} requires eccentricity to be lower than {}. ").format(
                self._data['scheme'], ECCENTRICITY_LIMIT
            )
            msg += _("Submit with scheme MPC_COMET to use your eccentricity of {}.").format(
                self._data['eccentricity']
            )
            self.error_dict['scheme'] = msg


class SatelliteTargetHelper(BaseTargetHelper):
    def __init__(self, target):
        self.fields = (
            'name', 'type', 'altitude', 'azimuth', 'diff_altitude_rate', 'diff_azimuth_rate',
            'diff_epoch', 'diff_altitude_acceleration', 'diff_azimuth_acceleration'
        )
        self.required_fields = self.fields
        self.fields += ()
        self.defaults = {}
        super().__init__(target)


TARGET_TYPE_HELPER_MAP = {
    'ICRS': ICRSTargetHelper,
    'ORBITAL_ELEMENTS': OrbitalElementsTargetHelper,
    'SATELLITE': SatelliteTargetHelper,
    'HOUR_ANGLE': ICRSTargetHelper,
}
