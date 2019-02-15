from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from datetime import timedelta

from observation_portal.requestgroups.models import Request, Configuration
from observation_portal.common.configdb import configdb


class Observation(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('IN_PROGRESS', 'IN_PROGRESS'),
        ('COMPLETED', 'COMPLETED'),
        ('CANCELED', 'CANCELED'),
        ('ABORTED', 'ABORTED'),
        ('FAILED', 'FAILED')
    )

    request = models.ForeignKey(Request, on_delete=models.PROTECT)
    site = models.CharField(
        max_length=10,
        help_text='3 character site code'
    )
    enclosure = models.CharField(
        max_length=10,
        help_text='4 character enclosure code'
    )
    telescope = models.CharField(
        max_length=10,
        help_text='4 character telescope code'
    )
    start = models.DateTimeField(
        db_index=True,
        help_text='Start time of observation'
    )
    end = models.DateTimeField(
        help_text='End time of observation'
    )
    modified = models.DateTimeField(
        auto_now=True, db_index=True,
        help_text='Time when this Observation was last changed'
    )
    created = models.DateTimeField(
        auto_now_add=True,
        help_text='Time when this Observation was created'
    )

    @property
    def state(self):
        states = [config_status.state for config_status in self.configuration_statuses.all()]
        if all([state == 'PENDING' for state in states]):
            return 'PENDING'
        elif (any([state == 'PENDING' or state == 'ATTEMPTED' for state in states]) and
              self.end < (timezone.now() - timedelta(minutes=5))):
            return 'IN_PROGRESS'
        elif any([state == 'FAILED' for state in states]):
            return 'FAILED'
        elif any([state == 'ABORTED' for state in states]):
            return 'ABORTED'
        elif any([state == 'CANCELED' for state in states]):
            return 'CANCELED'
        elif any([state == 'COMPLETED' for state in states]):
            return 'COMPLETED'
        else:
            return 'UNKNOWN'

    @classmethod
    def cancel(self, observations):
        pass


class ConfigurationStatus(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('ATTEMPTED', 'ATTEMPTED'),
        ('COMPLETED', 'COMPLETED'),
        ('CANCELED', 'CANCELED'),
        ('ABORTED', 'ABORTED'),
        ('FAILED', 'FAILED')
    )

    configuration = models.ForeignKey(Configuration, related_name='configuration_status', on_delete=models.PROTECT)
    observation = models.ForeignKey(Observation, related_name='configuration_statuses', on_delete=models.CASCADE)
    instrument_name = models.CharField(
        max_length=255,
        help_text='The specific instrument used to observe the corresponding Configuration'
    )
    guide_camera_name = models.CharField(
        max_length=255, default='', blank=True,
        help_text='The specific autoguider camera name to observe in the corresponding Configuration'
    )
    state = models.CharField(
        max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0],
        help_text='Current state of this RequestGroup'
    )
    modified = models.DateTimeField(
        auto_now=True,
        help_text='Time when this Configuration was last changed'
    )
    created = models.DateTimeField(
        auto_now_add=True,
        help_text='Time when this Configuration was created'
    )

    class Meta:
        unique_together = ('configuration', 'observation')
        verbose_name_plural = 'Configuration statuses'


class Summary(models.Model):
    configuration_status = models.OneToOneField(ConfigurationStatus, related_name='summary',
                                                on_delete=models.CASCADE)
    start = models.DateTimeField(
        db_index=True,
        help_text='Actual start time of configuration'
    )
    end = models.DateTimeField(
        help_text='Actual end time of configuration'
    )
    modified = models.DateTimeField(
        auto_now=True,
        help_text='Time when this Event was last changed'
    )
    created = models.DateTimeField(
        auto_now_add=True,
        help_text='Time when this Event was created'
    )
    state = models.CharField(
        max_length=50,
        help_text='The overall state of the set of events'
    )
    reason = models.CharField(
        max_length=200, default='', blank=True,
        help_text='If state is not COMPLETED, this contains the failure reason'
    )
    time_completed = models.FloatField(
        help_text='The seconds of exposure time completed for this configuration'
    )
    events = JSONField(
        default=dict, blank=True,
        help_text='Raw set of telescope events during this observation, in json format'
    )

    class Meta:
        verbose_name_plural = 'Summaries'

