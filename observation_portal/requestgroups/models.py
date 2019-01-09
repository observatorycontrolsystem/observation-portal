from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.utils.functional import cached_property
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from django.forms.models import model_to_dict
import requests
import logging

from valhalla.proposals.models import Proposal, TimeAllocationKey
from valhalla.userrequests.external_serializers import BlockSerializer
from valhalla.userrequests.target_helpers import TARGET_TYPE_HELPER_MAP
from valhalla.common.rise_set_utils import get_rise_set_target
from valhalla.userrequests.request_utils import return_paginated_results
from valhalla.userrequests.duration_utils import (get_request_duration, get_molecule_duration, get_total_duration_dict,
                                                  get_semester_in)

logger = logging.getLogger(__name__)


class RequestGroup(models.Model):
    NORMAL = 'NORMAL'
    RAPID_RESPONSE = 'RAPID_RESPONSE'
    TIME_CRITICAL = 'TIME_CRITICAL'

    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('COMPLETED', 'COMPLETED'),
        ('WINDOW_EXPIRED', 'WINDOW_EXPIRED'),
        ('CANCELED', 'CANCELED'),
    )

    OPERATOR_CHOICES = (
        ('SINGLE', 'SINGLE'),
        ('MANY', 'MANY'),
    )

    OBSERVATION_TYPES = (
        ('NORMAL', NORMAL),
        ('RAPID_RESPONSE', RAPID_RESPONSE),
        ('TIME_CRITICAL', TIME_CRITICAL)
    )

    submitter = models.ForeignKey(User, on_delete=models.CASCADE)
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE)
    group_name = models.CharField(max_length=50)
    observation_type = models.CharField(max_length=40, choices=OBSERVATION_TYPES)
    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES)
    ipp_value = models.FloatField(validators=[MinValueValidator(0.5), MaxValueValidator(2.0)])
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    state = models.CharField(max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0])
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return self.get_id_display()

    def get_id_display(self):
        return str(self.id)

    def get_absolute_url(self):
        return reverse('requestgroups:detail', kwargs={'pk': self.pk})

    @property
    def as_dict(self):
        ret_dict = model_to_dict(self)
        ret_dict['submitter'] = self.submitter.username
        ret_dict['proposal'] = self.proposal.id
        ret_dict['requests'] = [r.as_dict for r in self.requests.all()]
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
            duration = get_total_duration_dict(self.as_dict)
            cache.set('requestgroup_duration_{}'.format(self.id), duration, 86400 * 30 * 6)
            return duration
        else:
            return cached_duration


class Request(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('COMPLETED', 'COMPLETED'),
        ('WINDOW_EXPIRED', 'WINDOW_EXPIRED'),
        ('CANCELED', 'CANCELED'),
    )

    SERIALIZER_EXCLUDE = ('group',)

    group = models.ForeignKey(RequestGroup, related_name='requests', on_delete=models.CASCADE)
    observation_note = models.CharField(max_length=255, default='', blank=True)
    state = models.CharField(max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0])
    modified = models.DateTimeField(auto_now=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    # Minimum completable block threshold (percentage, 0-100)
    acceptability_threshold = models.FloatField(default=90.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.get_id_display()

    def get_id_display(self):
        return str(self.id)

    @property
    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        ret_dict['duration'] = self.duration
        ret_dict['configurations'] = [c.as_dict for c in self.configurations.all()]
        ret_dict['location'] = self.location.as_dict
        ret_dict['windows'] = [w.as_dict for w in self.windows.all()]
        return ret_dict

    @cached_property
    def duration(self):
        cached_duration = cache.get('request_duration_{}'.format(self.id))
        if not cached_duration:
            duration = get_request_duration({'configurations': [c.as_dict for c in self.configurations.all()]})
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
        return TimeAllocationKey(self.semester.id, self.configurations.first().instrument_configs.first().name)

    @property
    def timeallocation(self):
        return self.group.proposal.timeallocation_set.get(
            semester__start__lte=self.min_window_time,
            semester__end__gte=self.max_window_time,
            instrument_name=self.configurations.first().instrument_configs.first().name
        )


class Location(models.Model):
    TELESCOPE_CLASSES = (
        ('2m0', '2m0'),
        ('1m0', '1m0'),
        ('0m8', '0m8'),
        ('0m4', '0m4'),
    )

    SERIALIZER_EXCLUDE = ('request', 'id')

    request = models.OneToOneField(Request, on_delete=models.CASCADE)
    telescope_class = models.CharField(max_length=20, choices=TELESCOPE_CLASSES)
    site = models.CharField(max_length=20, default='', blank=True)
    observatory = models.CharField(max_length=20, default='', blank=True)
    telescope = models.CharField(max_length=20, default='', blank=True)

    class Meta:
        ordering = ('id',)

    @property
    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        ret_dict = {field: value for field, value in ret_dict.items() if value}
        return ret_dict

    def __str__(self):
        return '{}.{}.{}'.format(self.site, self.observatory, self.telescope)


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
        ('SIDEREAL', 'SIDEREAL'),
        ('NON_SIDEREAL', 'NON_SIDEREAL'),
        ('STATIC', 'STATIC'),
        ('SATELLITE', 'SATELLITE'),
    )

    SERIALIZER_EXCLUDE = ('request', 'id')

    name = models.CharField(max_length=50)
    request = models.OneToOneField(Request, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=POINTING_TYPES)

    # Coordinate modes
    roll = models.FloatField(null=True, blank=True)
    pitch = models.FloatField(null=True, blank=True)
    hour_angle = models.FloatField(null=True, blank=True)
    ra = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])
    dec = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)])
    altitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(90.0)])
    azimuth = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])

    # Pointing details
    coordinate_system = models.CharField(max_length=255, default='', blank=True)
    equinox = models.CharField(max_length=20, default='', blank=True)
    proper_motion_ra = models.FloatField(null=True, blank=True, validators=[MaxValueValidator(20000)])
    proper_motion_dec = models.FloatField(null=True, blank=True, validators=[MaxValueValidator(20000)])
    epoch = models.FloatField(max_length=20, null=True, blank=True, validators=[MaxValueValidator(2100)])
    parallax = models.FloatField(null=True, blank=True, validators=[MaxValueValidator(2000)])

    # Nonsidereal rate
    diff_pitch_rate = models.FloatField(verbose_name='Differential Pitch Rate (arcsec/s)', null=True, blank=True)
    diff_roll_rate = models.FloatField(verbose_name='Differential Roll Rate  (arcsec/s)', null=True, blank=True)
    diff_epoch_rate = models.FloatField(verbose_name='Reference time for non-sidereal motion (MJD)', null=True,
                                        blank=True)

    # Satellite Fields
    diff_pitch_acceleration = models.FloatField(verbose_name='Differential Pitch Acceleration (arcsec/s^2)', null=True,
                                                blank=True)
    diff_roll_acceleration = models.FloatField(verbose_name='Differential Role Acceleration (arcsec/s^2)', null=True,
                                               blank=True)

    # Orbital elements
    scheme = models.CharField(verbose_name='Orbital Element Scheme', max_length=50, choices=ORBITAL_ELEMENT_SCHEMES,
                              default='', blank=True)
    epochofel = models.FloatField(verbose_name='Epoch of elements (MJD)', null=True, blank=True,
                                  validators=[MinValueValidator(10000), MaxValueValidator(100000)])
    orbinc = models.FloatField(verbose_name='Orbital inclination (deg)', null=True, blank=True,
                               validators=[MinValueValidator(0.0), MaxValueValidator(180.0)])
    longascnode = models.FloatField(verbose_name='Longitude of ascending node (deg)', null=True, blank=True,
                                    validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])
    longofperih = models.FloatField(verbose_name='Longitude of perihelion (deg)', null=True, blank=True,
                                    validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])
    argofperih = models.FloatField(verbose_name='Argument of perihelion (deg)', null=True, blank=True,
                                   validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])
    meandist = models.FloatField(verbose_name='Mean distance (AU)', null=True, blank=True)
    perihdist = models.FloatField(verbose_name='Perihelion distance (AU)', null=True, blank=True)
    eccentricity = models.FloatField(verbose_name='Eccentricity', null=True, blank=True,
                                     validators=[MinValueValidator(0.0)])
    meanlong = models.FloatField(verbose_name='Mean longitude (deg)', null=True, blank=True)
    meananom = models.FloatField(verbose_name='Mean anomaly (deg)', null=True, blank=True,
                                 validators=[MinValueValidator(0.0), MaxValueValidator(360.0)])
    dailymot = models.FloatField(verbose_name='Daily motion (deg)', null=True, blank=True)
    epochofperih = models.FloatField(verbose_name='Epoch of perihelion (MJD)', null=True, blank=True,
                                     validators=[MinValueValidator(10000), MaxValueValidator(100000)])

    extra_params = JSONField()

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Target {}: {} type'.format(self.id, self.type)

    @property
    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        target_helper = TARGET_TYPE_HELPER_MAP[ret_dict['type'].upper()](ret_dict)
        ret_dict = {k: ret_dict.get(k) for k in target_helper.fields}
        return ret_dict

    @property
    def rise_set_target(self):
        return get_rise_set_target(self.as_dict)


class Window(models.Model):
    SERIALIZER_EXCLUDE = ('request', 'id')

    request = models.ForeignKey(Request, related_name='windows', on_delete=models.CASCADE)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ('id',)

    @property
    def as_dict(self):
        return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)

    def __str__(self):
        return 'Window {}: {} to {}'.format(self.id, self.start, self.end)


class Configuration(models.Model):
    TYPES = (
        ('EXPOSE', 'EXPOSE'),
        ('SKY_FLAT', 'SKY_FLAT'),
        ('STANDARD', 'STANDARD'),
        ('ARC', 'ARC'),
        ('LAMP_FLAT', 'LAMP_FLAT'),
        ('SPECTRUM', 'SPECTRUM'),
        ('AUTO_FOCUS', 'AUTO_FOCUS'),
        ('TRIPLE', 'TRIPLE'),
        ('NRES_TEST', 'NRES_TEST'),
        ('NRES_SPECTRUM', 'NRES_SPECTRUM'),
        ('NRES_EXPOSE', 'NRES_EXPOSE'),
        ('ENGINEERING', 'ENGINEERING'),
        ('SCRIPT', 'SCRIPT')
    )

    SERIALIZER_EXCLUDE = ('request', 'id')

    request = models.ForeignKey(Request, related_name='configurations', on_delete=models.CASCADE)

    # The type of configuration being requested.
    # Valid types are in TYPES
    type = models.CharField(max_length=50, choices=TYPES)

    extra_params = JSONField()
    # Used for ordering the configurations within an Observation
    priority = models.IntegerField(default=500)

    # Other options
    defocus = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-3.0), MaxValueValidator(3.0)])

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Configuration {0}: {1} type'.format(self.id, self.type)

    @property
    def as_dict(self):
        cdict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
	cdict['instrument_configs'] = [ic.as_dict for ic in self.instrument_configs.all()]
 	cdict['acquisition_config'] = self.acquisition_config.as_dict
	cdict['guiding_config'] = self.guiding_config.as_dict
	return cdict

    @cached_property
    def duration(self):
        return get_configuration_duration(self.as_dict)


class InstrumentConfig(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'configuration')
    configuration = models.ForeignKey(Configuration, related_name='instrument_configs', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    optical_elements = JSONField()
    mode = models.CharField(max_length=50, default='', blank=True)
    exposure_time = models.FloatField(validators=[MinValueValidator(0.01)])
    exposure_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    bin_x = models.PositiveSmallIntegerField(default=1, blank=True)
    bin_y = models.PositiveSmallIntegerField(default=1, blank=True)
    rot_mode = models.CharField(max_length=50, default='', blank=True)
    rot_angle = models.FloatField(default=0.0, blank=True)
    extra_params = JSONField()

    class Meta:
	ordering = ('id',)

    @property
    def as_dict(self):
	ic = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
	ic['rois'] = [roi.as_dict for roi in self.rois.all()]
	return ic

    @cached_property
    def duration(self):
	return get_instrument_configuration_duration(self.as_dict)


class ROI(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'instrument_config')
    instrument_config = models.ForeignKey(InstrumentConfig, related_name='rois', on_delete=models.CASCADE)
    x1 = models.PositiveIntegerField(null=True, blank=True)  # Sub Frame X start pixel
    x2 = models.PositiveIntegerField(null=True, blank=True)  # Sub Frame X end pixel
    y1 = models.PositiveIntegerField(null=True, blank=True)  # Sub Frame Y start pixel
    y2 = models.PositiveIntegerField(null=True, blank=True)  # Sub Frame Y end pixel

    class Meta:
	ordering = ('id',)

    @property
    def as_dict(self):
  	return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)


class GuidingConfig(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'configuration')
    STATES = (
        ('OPTIONAL', 'OPTIONAL'),
        ('ON', 'ON'),
        ('OFF', 'OFF')
    )

    configuration = models.OneToOneField(Configuration, related_name='guiding_config', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=50, choices=STATES, default=STATES[0][0])
    optical_elements = JSONField()
    exposure_time = models.FloatField(validators=[MinValueValidator(0.01)])
    extra_params = JSONField()

    class Meta:
	ordering = ('id',)

    @property
    def as_dict(self):
	return model_to_dict(self, exclude=self.SERIALIZER_EXClUDE)


class AcquisitionConfig(models.Model):
    SERIALIZER_EXCLUDE = ('id', 'configuration')
    STATES = (
        ('OFF', 'OFF'),
        ('ON', 'ON')
    )

    configuration = models.OneToOneField(Configuration, related_name='acquisition_config', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=50, choices=STATES, default=STATES[0][0])
    extra_params = JSONField()

    class Meta:
	ordering = ('id',)

    @property
    def as_dict(self):
	return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)


class Constraints(models.Model):
    SERIALIZER_EXCLUDE = ('configuration', 'id')

    configuration = models.OneToOneField(Configuration, on_delete=models.CASCADE)
    max_airmass = models.FloatField(default=1.6, validators=[MinValueValidator(1.0), MaxValueValidator(25.0)])
    min_lunar_distance = models.FloatField(default=30.0, validators=[MinValueValidator(0.0), MaxValueValidator(180.0)])
    max_lunar_phase = models.FloatField(null=True, blank=True)
    max_seeing = models.FloatField(null=True, blank=True)
    min_transparency = models.FloatField(null=True, blank=True)
    extra_params = JSONField()

    class Meta:
        ordering = ('id',)
        verbose_name_plural = 'Constraints'

    @property
    def as_dict(self):
        return model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)

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
