from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save

from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.common.state_changes import on_request_state_change, on_requestgroup_state_change
from observation_portal.proposals.notifications import requestgroup_notifications, request_notifications


@receiver(pre_save, sender=RequestGroup)
def cb_requestgroup_pre_save(sender, instance, *args, **kwargs):
    # instance has the new data, query the model for the current data
    # TODO refactor and make clear what is actually happening here
    if instance.id:
        # This is an update to the model
        current_data = RequestGroup.objects.get(pk=instance.pk)
        on_requestgroup_state_change(current_data.state, instance)


@receiver(pre_save, sender=Request)
def cb_request_pre_save(sender, instance, *args, **kwargs):
    # instance has the new data, query the model for the current data
    # TODO refactor and make clear what is actually happening here
    if instance.id:
        # This is an update to the model
        current_data = Request.objects.get(pk=instance.pk)
        on_request_state_change(current_data.state, instance)


@receiver(post_save, sender=RequestGroup)
def cb_requestgroup_send_notifications(sender, instance, *args, **kwargs):
    requestgroup_notifications(instance)

@receiver(post_save, sender=Request)
def cb_request_send_notifications(sender, instance, *args, **kwargs):
    request_notifications(instance)
