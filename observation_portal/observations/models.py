from django.db import models
from django.forms.models import model_to_dict
from django.utils import timezone
from django.core.cache import cache
from django.utils.module_loading import import_string
from django.conf import settings
from datetime import timedelta
from collections import defaultdict
import copy

from observation_portal.requestgroups.models import Request, RequestGroup, Configuration, Location
import logging

logger = logging.getLogger()


def observation_as_dict(instance, no_request=False):
    ret_dict = model_to_dict(instance)
    if no_request:
        ret_dict['configuration_statuses'] = [config_status.as_dict() for config_status in instance.configuration_statuses.all()]
    else:
        ret_dict['request'] = instance.request.as_dict(for_observation=True)
        ret_dict['proposal'] = instance.request.request_group.proposal.id
        ret_dict['submitter'] = instance.request.request_group.submitter.username
        ret_dict['name'] = instance.request.request_group.name
        ret_dict['ipp_value'] = instance.request.request_group.ipp_value
        ret_dict['observation_type'] = instance.request.request_group.observation_type
        ret_dict['request_group_id'] = instance.request.request_group.id
        ret_dict['created'] = instance.created
        ret_dict['modified'] = instance.modified
        ret_dict['request']['configurations'] = get_expanded_configurations(instance, ret_dict['request']['configurations'])
    return ret_dict


def get_expanded_configurations(observation, configurations):
    ''' Gets set of expanded configurations with configuration details filled in for a given observation
    '''
    expanded_configurations = []
    configuration_status_by_config = defaultdict(list)
    # First arrange the configuration statuses by Configuration they apply to in the order they apply
    for config_status in observation.configuration_statuses.all():
        configuration_status_by_config[config_status.configuration.id].append(config_status)
    # Loop over configuration_repeats and then over each Configuration in order to add that configuration to
    # the return set with the configuration_status fields added in.
    for repeat_index in range(observation.request.configuration_repeats):
        for configuration in configurations:
            # First deepcopy the configuration details - these will be modified
            expanded_configurations.append(copy.deepcopy(configuration))
            # Fill in some extra fields on the configuration using the configuration status
            config_status = configuration_status_by_config[configuration['id']][repeat_index]
            expanded_configurations[-1]['configuration_status'] = config_status.id
            expanded_configurations[-1]['state'] = config_status.state
            expanded_configurations[-1]['instrument_name'] = config_status.instrument_name
            expanded_configurations[-1]['guide_camera_name'] = config_status.guide_camera_name
            expanded_configurations[-1]['priority'] += (repeat_index * len(configurations))
            if hasattr(config_status, 'summary'):
                expanded_configurations[-1]['summary'] = config_status.summary.as_dict()
            else:
                expanded_configurations[-1]['summary'] = {}
    return expanded_configurations


def configurationstatus_as_dict(instance):
    ret_dict = model_to_dict(instance, exclude=instance.SERIALIZER_EXCLUDE)
    if hasattr(instance, 'summary'):
        ret_dict['summary'] = instance.summary.as_dict()
    else:
        ret_dict['summary'] = {}
    return ret_dict


def summary_as_dict(instance):
    ret_dict = model_to_dict(instance, exclude=instance.SERIALIZER_EXCLUDE)
    return ret_dict


class Observation(models.Model):
    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('IN_PROGRESS', 'IN_PROGRESS'),
        ('NOT_ATTEMPTED', 'NOT_ATTEMPTED'),
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
    priority = models.PositiveIntegerField(
        default=10,
        help_text='Priority (lower is better) for overlapping observations'
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

    @staticmethod
    def cancel(observations):
        now = timezone.now()

        observation_ids_to_delete = [observation.id for observation in observations if
                                     observation.start >= now + timedelta(hours=72)]
        _, deleted_observations = Observation.objects.filter(id__in=observation_ids_to_delete).delete()

        observation_ids_to_cancel = [observation.id for observation in observations if
                                     now < observation.start < now + timedelta(hours=72)]
        canceled = observations.filter(pk__in=observation_ids_to_cancel).update(state='CANCELED', modified=now)

        observation_ids_to_abort = [observation.id for observation in observations if
                                    observation.start <= now < observation.end]
        aborted = observations.filter(pk__in=observation_ids_to_abort).update(state='ABORTED', modified=now)

        return deleted_observations.get('observations.Observation', 0) + canceled + aborted

    def update_end_time(self, new_end_time):
        if new_end_time > self.start:
            # Only update the end time if it is > start time
            old_end_time = self.end
            self.end = new_end_time
            self.save()
            # Cancel observations that used to be under this observation
            if new_end_time > old_end_time:
                observations = Observation.objects.filter(
                    site=self.site,
                    enclosure=self.enclosure,
                    telescope=self.telescope,
                    start__lte=self.end,
                    start__gte=old_end_time,
                    state='PENDING'
                )
                if self.request.request_group.observation_type != RequestGroup.RAPID_RESPONSE:
                    observations = observations.exclude(
                        request__request_group__observation_type=RequestGroup.RAPID_RESPONSE
                    )
                num_canceled = Observation.cancel(observations)
                logger.info(
                    f"updated end time for observation {self.id} to {self.end}. "
                    f"Canceled {num_canceled} overlapping observations."
                )
            try:
                telescope_class = self.request.location.telescope_class
                cache.set(f"observation_portal_last_change_time_{telescope_class}", timezone.now(), None)
            except Location.DoesNotExist:
                pass
            cache.set('observation_portal_last_change_time_all', timezone.now(), None)
        return self

    @staticmethod
    def delete_old_observations(cutoff):
        observations = Observation.objects.filter(start__lt=cutoff, end__lt=cutoff, state='CANCELED').exclude(
            configuration_statuses__state__in=['ATTEMPTED', 'FAILED', 'COMPLETED']
        )
        logger.warning('There are {} observations to be deleted. Only the first 100,000 will be deleted this run'.format(observations.count()))
        total_deleted = 0
        total_obs_deleted = 0
        total_cs_deleted = 0
        total_sm_deleted = 0
        for observation in observations[:100000]:
            num_deleted, deleted_dict = observation.delete()
            total_deleted += num_deleted
            total_obs_deleted += deleted_dict.get('observations.Observation', 0)
            total_cs_deleted += deleted_dict.get('observations.ConfigurationStatus', 0)
            total_sm_deleted += deleted_dict.get('observations.Summary', 0)

        logger.warning('Deleted {} objects: {} observations, {} configuration_statuses, and {} summaries'.format(
            total_deleted, total_obs_deleted, total_cs_deleted, total_sm_deleted
        ))

    def as_dict(self, no_request=False):
        return import_string(settings.AS_DICT['observations']['Observation'])(self, no_request=no_request)

    # Returns the current configuration repeat we are within the request for this configuration status
    def get_current_repeat(self, configuration_status_id):
        num_configurations = self.request.configurations.count()
        configuration_status_index = 0
        for cs in self.configuration_statuses.all():
            if cs.id == configuration_status_id:
                break
            configuration_status_index += 1
        return (configuration_status_index // num_configurations) + 1

    @property
    def instrument_types(self):
        return set(self.request.configurations.values_list('instrument_type', flat=True))


class ConfigurationStatus(models.Model):
    SERIALIZER_EXCLUDE = ('modified', 'created', 'observation', 'time_charged')

    STATE_CHOICES = (
        ('PENDING', 'PENDING'),
        ('ATTEMPTED', 'ATTEMPTED'),
        ('NOT_ATTEMPTED', 'NOT_ATTEMPTED'),
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
    time_charged = models.FloatField(
        default=0.0,
        blank=True,
        help_text='Time in fractional hours that was debited from a TimeAllocation for this configuration'
    )
    modified = models.DateTimeField(
        auto_now=True,
        help_text='Time when this Configuration Status was last changed'
    )
    created = models.DateTimeField(
        auto_now_add=True,
        help_text='Time when this Configuration Status was created'
    )

    def as_dict(self):
        return import_string(settings.AS_DICT['observations']['ConfigurationStatus'])(self)

    class Meta:
        verbose_name_plural = 'Configuration statuses'
        ordering = ['id']


class Summary(models.Model):
    SERIALIZER_EXCLUDE = ('modified', 'created', 'configuration_status')

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
    events = models.JSONField(
        default=list, blank=True,
        help_text='Raw set of telescope events during this observation, in json format'
    )

    class Meta:
        verbose_name_plural = 'Summaries'

    def as_dict(self):
        return import_string(settings.AS_DICT['observations']['Summary'])(self)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.configuration_status.save()
