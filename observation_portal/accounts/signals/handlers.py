import json
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from django.conf import settings

from observation_portal.accounts.tasks import update_or_create_client_applications_user
from observation_portal.accounts.models import Profile


@receiver(post_save, sender=User)
def cb_user_post_save(sender, instance, created, *args, **kwargs):
    # Only update the user if it was not just created. If it was just created, we must wait until
    # the Profile is created to send the update since we need profile information, which should happen
    # immediately after user creation in our registration system.
    if not created and not (kwargs.get('update_fields') == frozenset({'last_login'})):
        user_json = json.dumps(import_string(settings.SERIALIZERS['accounts']['User'])(instance).data)
        update_or_create_client_applications_user.send(user_json)


@receiver(post_save, sender=Profile)
def cb_profile_post_save(sender, instance, created, *args, **kwargs):
    user_json = json.dumps(import_string(settings.SERIALIZERS['accounts']['User'])(instance.user).data)
    update_or_create_client_applications_user.send(user_json)
