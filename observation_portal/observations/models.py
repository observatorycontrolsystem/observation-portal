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
    state = models.CharField(
        max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0],
        help_text='Current State of this Observation'
    )

    @classmethod
    def cancel(self, observations):
        now = timezone.now()

        _, deleted_observations = observations.filter(start__gte=now + timedelta(hours=72)).delete()

        observation_ids_to_cancel = [observation.id for observation in observations if
                                     now < observation.start < now + timedelta(hours=72)]
        canceled = observations.filter(pk__in=observation_ids_to_cancel).update(state='CANCELED', modified=now)

        observation_ids_to_abort = [observation.id for observation in observations if
                                    observation.start <= now < observation.end]
        aborted = observations.filter(pk__in=observation_ids_to_abort).update(state='ABORTED', modified=now)

        return deleted_observations.get('observations.Observation', 0) + canceled + aborted
        pass


class ConfigurationStatus(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('ATTEMPTED', 'ATTEMPTED'),
        ('COMPLETED', 'COMPLETED'),
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
        help_text='Current state of this Configuration Status'
    )
    modified = models.DateTimeField(
        auto_now=True,
        help_text='Time when this Configuration Status was last changed'
    )
    created = models.DateTimeField(
        auto_now_add=True,
        help_text='Time when this Configuration Status was created'
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

