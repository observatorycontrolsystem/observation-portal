from django.db import models
from django.contrib.postgres.fields import JSONField
from django.forms.models import model_to_dict
from django.utils import timezone
from datetime import timedelta

from observation_portal.requestgroups.models import Request, Configuration


class Observation(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('IN_PROGRESS', 'IN_PROGRESS'),
        ('COMPLETED', 'COMPLETED'),
        ('CANCELED', 'CANCELED'),
        ('ABORTED', 'ABORTED'),
        ('FAILED', 'FAILED')
    )

    request = models.ForeignKey(
        Request, on_delete=models.PROTECT
    )
    site = models.CharField(
        max_length=10, db_index=True,
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
        max_length=40, choices=STATE_CHOICES, default=STATE_CHOICES[0][0], db_index=True,
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

    def as_dict(self):
        ret_dict = model_to_dict(self)
        ret_dict['request'] = self.request.as_dict(for_observation=True)
        ret_dict['proposal'] = self.request.request_group.proposal.id
        ret_dict['submitter'] = self.request.request_group.submitter.username
        ret_dict['name'] = self.request.request_group.name
        ret_dict['ipp_value'] = self.request.request_group.ipp_value
        ret_dict['observation_type'] = self.request.request_group.observation_type
        ret_dict['request_group_id'] = self.request.request_group.id
        configuration_status_by_config = {config_status.configuration.id: config_status
                                          for config_status in self.configuration_statuses.all()}
        for configuration in ret_dict['request']['configurations']:
            config_status = configuration_status_by_config[configuration['id']]
            configuration['configuration_status'] = config_status.id
            configuration['state'] = config_status.state
            configuration['instrument_name'] = config_status.instrument_name
            configuration['guide_camera_name'] = config_status.guide_camera_name
            try:
                configuration['summary'] = config_status.summary.as_dict()
            except Exception:
                configuration['summary'] = {}
        return ret_dict

    @property
    def instrument_types(self):
        return set(
            Configuration.objects.filter(
                configuration_status__in=self.configuration_statuses.all()
            ).values_list('instrument_type', flat=True)
        )


class ConfigurationStatus(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('ATTEMPTED', 'ATTEMPTED'),
        ('COMPLETED', 'COMPLETED'),
        ('FAILED', 'FAILED')
    )

    configuration = models.ForeignKey(
        Configuration, related_name='configuration_status', on_delete=models.PROTECT
    )
    observation = models.ForeignKey(
        Observation, related_name='configuration_statuses', on_delete=models.CASCADE
    )
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
    SERIALIZER_EXCLUDE = ('modified', 'created')

    configuration_status = models.OneToOneField(
        ConfigurationStatus, null=True, blank=True, related_name='summary', on_delete=models.CASCADE
    )

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

    def as_dict(self):
        ret_dict = model_to_dict(self, exclude=self.SERIALIZER_EXCLUDE)
        return ret_dict

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.configuration_status.save()
