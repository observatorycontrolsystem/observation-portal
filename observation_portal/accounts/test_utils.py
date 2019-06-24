from mixer.backend.django import mixer
from django.utils import timezone

from observation_portal.accounts.models import User, Profile


def blend_user(user_params=None, profile_params=None):
    if user_params:
        user = mixer.blend(User, **user_params)
    else:
        user = mixer.blend(User, is_staff=False, is_superuser=False)

    if profile_params:
        mixer.blend(Profile, user=user, terms_accepted=timezone.now(), **profile_params)
    else:
        mixer.blend(Profile, user=user, terms_accepted=timezone.now())

    return user
