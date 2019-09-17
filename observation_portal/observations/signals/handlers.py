from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

from observation_portal.observations.models import ConfigurationStatus, Summary
from observation_portal.observations.time_accounting import on_summary_update_time_accounting
from observation_portal.common.state_changes import on_configuration_status_state_change


@receiver(post_save, sender=ConfigurationStatus)
def cb_configurationstatus_post_save(sender, instance, created, *args, **kwargs):
    # Ensure this is an update to the model and not a new model
    if not created:
        on_configuration_status_state_change(instance)


@receiver(pre_save, sender=Summary)
def cb_summary_pre_save(sender, instance, *args, **kwargs):
    # Update the time accounting on a summary update or creation
    if instance.id:
        current_summary = Summary.objects.get(pk=instance.pk)
    else:
        current_summary = None
    on_summary_update_time_accounting(current_summary, instance)
