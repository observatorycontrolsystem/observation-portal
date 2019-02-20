from django.dispatch import receiver
from django.db.models.signals import post_save

from observation_portal.observations.models import ConfigurationStatus
from observation_portal.observations.state_changes import on_configuration_state_change


@receiver(post_save, sender=ConfigurationStatus)
def cb_configurationstatus_pre_save(sender, instance, created, *args, **kwargs):
    # Ensure this is an update to the model and not a new model
    if not created:
        current_data = ConfigurationStatus.objects.get(pk=instance.pk)
        if current_data.state != instance.state:
            on_configuration_state_change(instance)
