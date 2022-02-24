from mixer.backend.django import mixer
from django.utils import timezone
from django.db.models.signals import post_save

from observation_portal.accounts.models import User, Profile
from observation_portal.common.test_helpers import disconnect_signal
from observation_portal.accounts.signals.handlers import cb_user_post_save, cb_profile_post_save


def blend_user(user_params=None, profile_params=None):
    with disconnect_signal(post_save, cb_user_post_save, User):
        with disconnect_signal(post_save, cb_profile_post_save, Profile):

            if user_params:
                user = mixer.blend(User, **user_params)
            else:
                user = mixer.blend(User, is_staff=False, is_superuser=False)

            if profile_params:
                mixer.blend(Profile, user=user, terms_accepted=timezone.now(), **profile_params)
            else:
                mixer.blend(Profile, user=user, terms_accepted=timezone.now())

            return user
