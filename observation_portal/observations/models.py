from django.db import models
from django.contrib.postgres.fields import JSONField

from observation_portal.requestgroups.models import Request, Configuration


class Observation(models.Model):
    request = models.ForeignKey(Request, on_delete=models.PROTECT)
    site = models.CharField(
        max_length=10,
        help_text='3 character site code'
    )
    observatory = models.CharField(
        max_length=10,
        help_text='3 character site code'
    )
    telescope = models.CharField(
        max_length=10,
        help_text='3 character site code'
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


class ConfigurationStatus(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('ATTEMPTED', 'ATTEMPTED'),
        ('COMPLETED', 'COMPLETED'),
        ('CANCELED', 'CANCELED'),
        ('FAILED', 'FAILED')
    )

    configuration = models.ForeignKey(Configuration, on_delete=models.PROTECT)
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE)
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


class Summary(models.Model):
    configuration_status = models.OneToOneField(ConfigurationStatus, on_delete=models.CASCADE)
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
        max_length=200, default='',
        help_text='If state is not COMPLETED, this contains the failure reason'
    )
    time_completed = models.FloatField(
        help_text='The seconds of exposure time completed for this configuration'
    )
    events = JSONField(
        help_text='Raw set of telescope events during this observation, in json format'
    )

