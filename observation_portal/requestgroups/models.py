from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.utils.functional import cached_property
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.utils import timezone
from django.urls import reverse
from django.forms.models import model_to_dict
from django.utils.functional import lazy
import logging

from observation_portal.common.configdb import configdb
from observation_portal.proposals.models import Proposal, TimeAllocationKey
from observation_portal.requestgroups.target_helpers import TARGET_TYPE_HELPER_MAP
from observation_portal.common.rise_set_utils import get_rise_set_target
from observation_portal.requestgroups.duration_utils import (
    get_request_duration,
    get_configuration_duration,
    get_complete_configurations_duration,
    get_instrument_configuration_duration,
    get_total_duration_dict,
    get_semester_in
)

logger = logging.getLogger(__name__)


class RequestGroup(models.Model):
    NORMAL = 'NORMAL'
    RAPID_RESPONSE = 'RAPID_RESPONSE'
    TIME_CRITICAL = 'TIME_CRITICAL'
    DIRECT = 'DIRECT'

    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('COMPLETED', 'COMPLETED'),
        ('WINDOW_EXPIRED', 'WINDOW_EXPIRED'),
        ('FAILURE_LIMIT_REACHED', 'FAILURE_LIMIT_REACHED'),
        ('CANCELED', 'CANCELED'),
    )

    OPERATOR_CHOICES = (
        ('SINGLE', 'SINGLE'),
        ('MANY', 'MANY'),
    )

    OBSERVATION_TYPES = (
        ('NORMAL', NORMAL),
        ('RAPID_RESPONSE', RAPID_RESPONSE),
        ('TIME_CRITICAL', TIME_CRITICAL),
        ('DIRECT', DIRECT)
    )

    submitter = models.ForeignKey(
        User, on_delete=models.CASCADE,
        help_text='The user that submitted this RequestGroup'
    )
    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE,
        help_text='The Proposal under which the observations for this RequestGroup are made'
    )
    name = models.CharField(
        max_length=50,
        help_text='Descriptive name for this RequestGroup. This string will be placed in the FITS header as the '
                  'GROUPID keyword value for all FITS frames originating from this RequestGroup.'
    )
    observation_type = models.CharField(
        max_length=40, choices=OBSERVATION_TYPES,
        help_text='The type of observations under this RequestGroup. Requests submitted with RAPID_RESPONSE '
                  'bypass normal scheduling and are executed immediately. Requests submitted with TIME_CRITICAL are '
                  'scheduled normally but with a high priority. These modes are only available if the Proposal was '
                  'granted special time. More information is located '
                  '<a href="https://lco.global/documentation/special-scheduling-modes/">here</a>.'
    )
    operator = models.CharField(
        max_length=20, choices=OPERATOR_CHOICES,
        help_text='Operator that describes how child Requests are scheduled. Use SINGLE if you have only one Request '
                  'and MANY if you have more than one.'
    )
    ipp_value = models.FloatField(
        validators=[MinValueValidator(0.5), MaxValueValidator(2.0)],
        help_text='A multiplier to the base priority of the Proposal for this RequestGroup and all child Requests. '
                  'A value > 1.0 will raise the priority and debit the Proposal ipp_time_available upon submission. '
                  'If a Request does not complete, the time debited for that Request is returned. A value < 1.0 will '
                  'lower the priority and credit the ipp_time_available of the Proposal up to the ipp_limit on the '
                  'successful completion of a Request. The value is generally set to 1.05. More information can be '
                  'found <a href="https://lco.global/files/User_Documentation/the_new_priority_factor.pdf">here</a>.'
    )
    created = models.DateTimeField(
        auto_now_add=True, db_index=True,
        help_text='Time when this RequestGroup was created'
    )
    state = models.CharField(
        max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0],
        help_text='Current state of this RequestGroup'
    )
    modified = models.DateTimeField(
        auto_now=True, db_index=True,
        help_text='Time when this RequestGroup was last changed'
    )

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return self.get_id_display()

    def get_id_display(self):
        return str(self.id)

    def get_absolute_url(self):
        return reverse('api:request_groups-detail', kwargs={'pk': self.pk})

    def as_dict(self):
        ret_dict = model_to_dict(self)
        ret_dict['created'] = self.created
        ret_dict['modified'] = self.modified
        ret_dict['submitter'] = self.submitter.username
        ret_dict['proposal'] = self.proposal.id
        ret_dict['requests'] = [r.as_dict() for r in self.requests.all()]
        return ret_dict

    @property
    def min_window_time(self):
        return min([request.min_window_time for request in self.requests.all()])

    @property
    def max_window_time(self):
        return max([request.max_window_time for request in self.requests.all()])

    @property
    def timeallocations(self):
        return self.proposal.timeallocation_set.filter(
            semester__start__lte=self.min_window_time,
            semester__end__gte=self.max_window_time,
        )

    @property
    def total_duration(self):
        cached_duration = cache.get('requestgroup_duration_{}'.format(self.id))
        if not cached_duration:
            duration = get_total_duration_dict(self.as_dict())
            cache.set('requestgroup_duration_{}'.format(self.id), duration, 86400 * 30 * 6)
            return duration
        else:
            return cached_duration


class Request(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('COMPLETED', 'COMPLETED'),
        ('WINDOW_EXPIRED', 'WINDOW_EXPIRED'),
        ('FAILURE_LIMIT_REACHED', 'FAILURE_LIMIT_REACHED'),
        ('CANCELED', 'CANCELED'),
    )

    SERIALIZER_EXCLUDE = ('request_group',)

    request_group = models.ForeignKey(
        RequestGroup, related_name='requests', on_delete=models.CASCADE,
        help_text='The RequestGroup to which this Request belongs'
    )
    observation_note = models.CharField(
        max_length=255, default='', blank=True,
        help_text='Text describing this Request'
    )
    state = models.CharField(
        max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0],
        help_text='Current state of this Request'
    )
    modified = models.DateTimeField(
        auto_now=True, db_index=True,
        help_text='Time at which this Request last changed'
    )
    created = models.DateTimeField(auto_now_add=True, help_text='Time at which the Request was created')

    # Minimum completable observation threshold
    acceptability_threshold = models.FloatField(
        default=90.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text='The percentage of this Request that must be completed to mark it as complete and avert '
                  'rescheduling. The percentage should be set to the lowest value for which the amount of data is '
                  'acceptable to meet the science goal of the Request. Defaults to 100 for FLOYDS observations and '
                  '90 for all other observations.'
    )

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.get_id_display()

    def get_id_display(self):
        return str(self.id)

    def as_dict(self, for_observation=False):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        ret_dict['modified'] = self.modified
        ret_dict['duration'] = self.duration
        ret_dict['configurations'] = [c.as_dict() for c in self.configurations.all()]
        if not for_observation:
            if self.request_group.observation_type == RequestGroup.DIRECT:
                if self.observation_set.count() > 0:
                    observation = self.observation_set.first()
                    ret_dict['location'] = {'site': observation.site, 'enclosure': observation.enclosure,
                                            'telescope': observation.telescope}
                    ret_dict['windows'] = [{'start': observation.start, 'end': observation.end}]
            else:
                ret_dict['location'] = self.location.as_dict() if hasattr(self, 'location') else {}
                ret_dict['windows'] = [w.as_dict() for w in self.windows.all()]
        return ret_dict

    @cached_property
    def duration(self):
        cached_duration = cache.get('request_duration_{}'.format(self.id))
        if not cached_duration:
            duration = get_request_duration({'configurations': [c.as_dict() for c in self.configurations.all()],
                                             'windows': [w.as_dict() for w in self.windows.all()]})
            cache.set('request_duration_{}'.format(self.id), duration, 86400 * 30 * 6)
            return duration
        else:
            return cached_duration

    @property
    def min_window_time(self):
        return min([window.start for window in self.windows.all()])

    @property
    def max_window_time(self):
        return max([window.end for window in self.windows.all()])

    @property
    def semester(self):
        return get_semester_in(self.min_window_time, self.max_window_time)

    @property
    def time_allocation_key(self):
        return TimeAllocationKey(self.semester.id, self.configurations.first().instrument_type)

    @property
    def timeallocations(self):
        return self.request_group.proposal.timeallocation_set.filter(
            semester__start__lte=self.min_window_time,
            semester__end__gte=self.max_window_time,
            instrument_type__in=[conf.instrument_type for conf in self.configurations.all()]
        )

    def get_remaining_duration(self, configurations_after_priority):
        request_dict = self.as_dict()
        start_time = (min([window['start'] for window in request_dict['windows']])
                      if 'windows' in request_dict and request_dict['windows'] else timezone.now())
        try:
            configurations = sorted(request_dict['configurations'], key=lambda x: x['priority'])
        except KeyError:
            configurations = request_dict['configurations']
        duration = get_complete_configurations_duration(
            configurations,
            start_time,
            configurations_after_priority
        )
        return duration


class Location(models.Model):
    SERIALIZER_EXCLUDE = ('request', 'id')

    request = models.OneToOneField(
        Request, on_delete=models.CASCADE,
        help_text='The Request to which this Location applies'
    )
    telescope_class = models.CharField(
        max_length=20,
        help_text='The telescope class on which to observe the Request. The class describes the aperture size, '
                  'e.g. 1m0 is a 1m telescope, and 0m4 is a 0.4m telescope.'
    )
    site = models.CharField(
        max_length=20, default='', blank=True,
        help_text='Three-letter site code indicating the site at which to observe the Request'
    )
    enclosure = models.CharField(
        max_length=20, default='', blank=True,
        help_text='Four-letter enclosure code indicating the enclosure from which to observe the Request'
    )
    telescope = models.CharField(
        max_length=20, default='', blank=True,
        help_text='Four-letter telescope code indicating the telescope on which to observe the Request'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        ret_dict = {field: value for field, value in ret_dict.items() if value}
        return ret_dict

    def __str__(self):
        return '{}.{}.{}'.format(self.site, self.enclosure, self.telescope)


class Window(models.Model):
    SERIALIZER_EXCLUDE = ('request', 'id')

    request = models.ForeignKey(
        Request, related_name='windows', on_delete=models.CASCADE,
        help_text='The Request to which this Window applies'
    )
    start = models.DateTimeField(
        db_index=True,
        help_text='The time when this observing Window starts'
    )
    end = models.DateTimeField(
        db_index=True,
        help_text='The time when this observing Window ends'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)

    def __str__(self):
        return 'Window {}: {} to {}'.format(self.id, self.start, self.end)


class Configuration(models.Model):
    TYPES = (
        ('EXPOSE', 'EXPOSE'),
        ('REPEAT_EXPOSE', 'REPEAT_EXPOSE'),
        ('SKY_FLAT', 'SKY_FLAT'),
        ('STANDARD', 'STANDARD'),
        ('ARC', 'ARC'),
        ('LAMP_FLAT', 'LAMP_FLAT'),
        ('SPECTRUM', 'SPECTRUM'),
        ('REPEAT_SPECTRUM', 'REPEAT_SPECTRUM'),
        ('AUTO_FOCUS', 'AUTO_FOCUS'),
        ('TRIPLE', 'TRIPLE'),
        ('NRES_TEST', 'NRES_TEST'),
        ('NRES_SPECTRUM', 'NRES_SPECTRUM'),
        ('REPEAT_NRES_SPECTRUM', 'REPEAT_NRES_SPECTRUM'),
        ('NRES_EXPOSE', 'NRES_EXPOSE'),
        ('NRES_DARK', 'NRES_DARK'),
        ('NRES_BIAS', 'NRES_BIAS'),
        ('ENGINEERING', 'ENGINEERING'),
        ('SCRIPT', 'SCRIPT'),
        ('BIAS', 'BIAS'),
        ('DARK', 'DARK')
    )

    SERIALIZER_EXCLUDE = ('request',)

    request = models.ForeignKey(
        Request, related_name='configurations', on_delete=models.CASCADE,
        help_text='The Request to which this Configuration belongs'
    )
    instrument_type = models.CharField(
        max_length=255,
        help_text='The instrument type used for the observations under this Configuration'
    )
    # The type of configuration being requested.
    # Valid types are in TYPES
    # TODO: Get the types from configdb
    type = models.CharField(
        max_length=50, choices=TYPES,
        help_text='The type of exposures for the observations under this Configuration'
    )

    repeat_duration = models.FloatField(
        verbose_name='configuration duration',
        blank=True,
        null=True,
        validators=[MinValueValidator(0.0)],
        help_text='The requested duration for this configuration to be repeated within. '
                  'Only applicable to REPEAT_* type configurations. Setting parameter fill_window '
                  'to True will cause this value to automatically be filled in to the max '
                  'possible given its visibility within the observing window.'
    )

    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra Configuration parameters'
    )
    # Used for ordering the configurations within an Observation
    priority = models.IntegerField(
        default=500,
        help_text='The order that the Configurations within a Request will be observed. Configurations with priorities '
                  'that are lower numbers are executed first.'
    )

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Configuration {0}: {1} type'.format(self.id, self.type)

    def as_dict(self):
        cdict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        cdict['instrument_configs'] = [ic.as_dict() for ic in self.instrument_configs.all()]
        cdict['constraints'] = self.constraints.as_dict()
        cdict['acquisition_config'] = self.acquisition_config.as_dict()
        cdict['guiding_config'] = self.guiding_config.as_dict()
        try:
            cdict['target'] = self.target.as_dict()
        except Exception:
            cdict['target'] = {}
        return cdict

    @cached_property
    def duration(self):
        return get_configuration_duration(self.as_dict())['duration']


class Target(models.Model):
    ORBITAL_ELEMENT_SCHEMES = (
        ('ASA_MAJOR_PLANET', 'ASA_MAJOR_PLANET'),
        ('ASA_MINOR_PLANET', 'ASA_MINOR_PLANET'),
        ('ASA_COMET', 'ASA_COMET'),
        ('JPL_MAJOR_PLANET', 'JPL_MAJOR_PLANET'),
        ('JPL_MINOR_PLANET', 'JPL_MINOR_PLANET'),
        ('MPC_MINOR_PLANET', 'MPC_MINOR_PLANET'),
        ('MPC_COMET', 'MPC_COMET'),
    )

    POINTING_TYPES = (
        ('ICRS', 'ICRS'),
        ('ORBITAL_ELEMENTS', 'ORBITAL_ELEMENTS'),
        ('HOUR_ANGLE', 'HOUR_ANGLE'),
        ('SATELLITE', 'SATELLITE'),
    )

    SERIALIZER_EXCLUDE = ('configuration', 'id')

    name = models.CharField(
        max_length=50,
        help_text='The name of this Target'
    )
    configuration = models.OneToOneField(
        Configuration, on_delete=models.CASCADE,
        help_text='The configuration to which this Target belongs'
    )
    type = models.CharField(
        max_length=255, choices=POINTING_TYPES,
        help_text='The type of this Target'
    )

    # Coordinate modes
    hour_angle = models.FloatField(
        null=True, blank=True,
        help_text='Hour angle of this Target'
    )
    ra = models.FloatField(
        verbose_name='right ascension', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Right ascension in decimal degrees'
    )
    dec = models.FloatField(
        verbose_name='declination', null=True, blank=True,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text='Declination in decimal degrees'
    )
    altitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(90.0)],
        help_text='Altitude of this Target'
    )
    azimuth = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Azimuth of this Target'
    )

    # Pointing details
    proper_motion_ra = models.FloatField(
        verbose_name='right ascension proper motion', null=True, blank=True, validators=[MaxValueValidator(20000)],
        help_text='Right ascension proper motion of the Target +/-33 mas/year. Defaults to 0.'
    )
    proper_motion_dec = models.FloatField(
        verbose_name='declination proper motion', null=True, blank=True, validators=[MaxValueValidator(20000)],
        help_text='Declination proper motion of the Target +/-33 mas/year. Defaults to 0.'
    )
    epoch = models.FloatField(
        max_length=20, null=True, blank=True, validators=[MaxValueValidator(2100)],
        help_text='Epoch in Modified Julian Days (MJD). Defaults to 2000.'
    )
    parallax = models.FloatField(
        null=True, blank=True, validators=[MaxValueValidator(2000)],
        help_text='Parallax of the Target ±0.45 mas, max 2000. Defaults to 0.'
    )

    # Nonsidereal rate
    diff_altitude_rate = models.FloatField(
        verbose_name='differential altitude rate', null=True, blank=True,
        help_text='Differential altitude rate (arcsec/s)'
    )
    diff_azimuth_rate = models.FloatField(
        verbose_name='differential azimuth rate', null=True, blank=True,
        help_text='Differential azimuth rate (arcsec/s)'
    )
    diff_epoch = models.FloatField(
        verbose_name='differential epoch', null=True, blank=True,
        help_text='Reference time for non-sidereal motion (MJD)'
    )

    # Satellite Fields
    diff_altitude_acceleration = models.FloatField(
        verbose_name='differential altitude acceleration', null=True, blank=True,
        help_text='Differential altitude acceleration (arcsec/s^2)'
    )
    diff_azimuth_acceleration = models.FloatField(
        verbose_name='differential azimuth acceleration', null=True, blank=True,
        help_text='Differential azimuth acceleration (arcsec/s^2)'
    )

    # Orbital elements
    scheme = models.CharField(
        verbose_name='orbital element scheme', max_length=50, choices=ORBITAL_ELEMENT_SCHEMES, default='', blank=True,
        help_text='The Target scheme to use'
    )
    epochofel = models.FloatField(
        verbose_name='epoch of elements', null=True, blank=True,
        validators=[MinValueValidator(10000), MaxValueValidator(100000)],
        help_text='The epoch of the orbital elements (MJD)'
    )
    orbinc = models.FloatField(
        verbose_name='orbital inclination', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(180.0)],
        help_text='Orbital inclination (angle in degrees)'
    )
    longascnode = models.FloatField(
        verbose_name='longitude of ascending node', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Longitude of ascending node (angle in degrees)'
    )
    longofperih = models.FloatField(
        verbose_name='longitude of perihelion', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Longitude of perihelion (angle in degrees)'
    )
    argofperih = models.FloatField(
        verbose_name='argument of perihelion', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Argument of perihelion (angle in degrees)'
    )
    meandist = models.FloatField(
        verbose_name='mean distance', null=True, blank=True,
        help_text='Mean distance (AU)'
    )
    perihdist = models.FloatField(
        verbose_name='perihelion distance', null=True, blank=True,
        help_text='Perihelion distance (AU)'
    )
    eccentricity = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0.0)],
        help_text='Eccentricity of the orbit'
    )
    meanlong = models.FloatField(
        verbose_name='mean longitude', null=True, blank=True,
        help_text='Mean longitude (angle in degrees)'
    )
    meananom = models.FloatField(
        verbose_name='mean anomaly', null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text='Mean anomaly (angle in degrees)'
    )
    dailymot = models.FloatField(
        verbose_name='daily motion', null=True, blank=True,
        help_text='Daily motion (angle in degrees)'
    )
    epochofperih = models.FloatField(
        verbose_name='epoch of perihelion', null=True, blank=True,
        validators=[MinValueValidator(10000), MaxValueValidator(100000)],
        help_text='Epoch of perihelion (MJD)'
    )

    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra Target parameters'
    )

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Target {}: {} type'.format(self.id, self.type)

    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        extra_params = ret_dict.get('extra_params', {})
        target_helper = TARGET_TYPE_HELPER_MAP[ret_dict['type'].upper()](ret_dict)
        ret_dict = {k: ret_dict.get(k) for k in target_helper.fields}
        ret_dict['extra_params'] = extra_params
        return ret_dict

    @property
    def rise_set_target(self):
        return get_rise_set_target(self.as_dict())


class InstrumentConfig(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'configuration')

    configuration = models.ForeignKey(
        Configuration, related_name='instrument_configs', on_delete=models.CASCADE,
        help_text='The Configuration to which this InstrumentConfig belongs'
    )
    optical_elements = JSONField(
        default=dict,
        blank=True,
        help_text='Specification of optical elements used for this InstrumentConfig'
    )
    mode = models.CharField(
        max_length=50, default='', blank=True,
        help_text='The mode of this InstrumentConfig'
    )
    exposure_time = models.FloatField(
        validators=[MinValueValidator(0.0)],
        help_text='Exposure time in seconds. A tool to aid in deciding on an exposure time is located '
                  '<a href="https://lco.global/files/etc/exposure_time_calculator.html">here</a>.'
    )
    exposure_count = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='The number of exposures to take. This field must be set to a value greater than 0.'
    )
    bin_x = models.PositiveSmallIntegerField(
        verbose_name='y binning', default=1, blank=True,
        help_text='Binning in the x dimension, defaults to the instrument default'
    )
    bin_y = models.PositiveSmallIntegerField(
        verbose_name='x binning', default=1, blank=True,
        help_text='Binning in the y dimension, defaults to the instrument default'
    )
    rotator_mode = models.CharField(
        verbose_name='rotation mode', max_length=50, default='', blank=True,
        help_text='(Spectrograph only) How the slit is positioned on the sky. If set to VFLOAT, atmospheric '
                  'dispersion is along the slit.'
    )
    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra InstrumentConfig parameters'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        ic = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        ic['rois'] = [roi.as_dict() for roi in self.rois.all()]
        return ic

    @cached_property
    def duration(self):
        return get_instrument_configuration_duration(self.as_dict(), self.configuration.instrument_type)


class RegionOfInterest(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'instrument_config')

    instrument_config = models.ForeignKey(
        InstrumentConfig, related_name='rois', on_delete=models.CASCADE,
        help_text='The InstrumentConfig to which this RegionOfInterest belongs'
    )
    x1 = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Sub-frame x start pixel'
    )
    x2 = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Sub-frame x end pixel'
    )
    y1 = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Sub-frame y start pixel'
    )
    y2 = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Sub-frame y end pixel'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)


class GuidingConfig(models.Model):
    OFF = 'OFF'

    SERIALIZER_EXCLUDE = ('id', 'configuration')

    configuration = models.OneToOneField(
        Configuration, related_name='guiding_config', on_delete=models.CASCADE,
        help_text='The Configuration to which this GuidingConfig belongs'
    )
    optional = models.BooleanField(
        default=True,
        help_text='Whether the guiding is optional or not'
    )
    mode = models.CharField(
        max_length=50, default='', blank=True,
        help_text='Guiding mode to use for the observations'
    )
    optical_elements = JSONField(
        default=dict,
        blank=True,
        help_text='Optical Element specification for this GuidingConfig'
    )
    exposure_time = models.FloatField(blank=True, null=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(120.0)],
        help_text='Guiding exposure time'
    )
    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra GuidingConfig parameters'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)


class AcquisitionConfig(models.Model):
    OFF = 'OFF'
    SERIALIZER_EXCLUDE = ('id', 'configuration')

    configuration = models.OneToOneField(
        Configuration, related_name='acquisition_config', on_delete=models.CASCADE,
        help_text='The Configuration to which this AcquisitionConfig belongs'
    )
    mode = models.CharField(
        max_length=50, default=OFF,
        help_text='AcquisitionConfig mode to use for the observations'
    )
    exposure_time = models.FloatField(blank=True, null=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(60.0)],
        help_text='Acquisition exposure time'
    )
    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra AcquisitionConfig parameters'
    )

    class Meta:
        ordering = ('id',)

    def as_dict(self):
        config = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        config = {field: value for field, value in config.items() if value is not None}
        return config


class Constraints(models.Model):
    SERIALIZER_EXCLUDE = ('configuration', 'id')

    configuration = models.OneToOneField(
        Configuration, on_delete=models.CASCADE,
        help_text='The Configuration to which these Constraints belong'
    )
    max_airmass = models.FloatField(
        verbose_name='maximum airmass', default=1.6, validators=[MinValueValidator(1.0), MaxValueValidator(25.0)],
        help_text='Maximum acceptable airmass. At zenith, the airmass equals 1 and increases with zenith distance. '
                  'Assumes a plane-parallel atmosphere. You can read about the considerations of setting the airmass '
                  'limit <a href="https://lco.global/documentation/airmass-limit/">here</a>.'
    )
    min_lunar_distance = models.FloatField(
        verbose_name='minimum lunar distance', default=30.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(180.0)],
        help_text='Minimum acceptable angular separation between the target and the moon in decimal degrees'
    )
    max_lunar_phase = models.FloatField(
        verbose_name='Maximum lunar phase', null=True, blank=True,
        help_text='Maximum acceptable lunar phase'
    )
    max_seeing = models.FloatField(
        verbose_name='maximum seeing', null=True, blank=True,
        help_text='Maximum acceptable seeing'
    )
    min_transparency = models.FloatField(
        verbose_name='minimum transparency', null=True, blank=True,
        help_text='Minimum acceptable transparency'
    )
    extra_params = JSONField(
        default=dict,
        blank=True,
        verbose_name='extra parameters',
        help_text='Extra Constraints parameters'
    )

    class Meta:
        ordering = ('id',)
        verbose_name_plural = 'Constraints'

    def as_dict(self):
        constraints = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        constraints = {field: value for field, value in constraints.items() if value is not None}
        return constraints

    def __str__(self):
        return 'Constraints {}: {} max airmass, {} min_lunar_distance'.format(self.id, self.max_airmass,
                                                                              self.min_lunar_distance)


class DraftRequestGroup(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modified']
        unique_together = ('author', 'proposal', 'title')

    def __str__(self):
        return 'Draft request by: {} for proposal: {}'.format(self.author, self.proposal)
