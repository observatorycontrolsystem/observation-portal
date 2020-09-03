from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response

from observation_portal.common.configdb import configdb


class LastScheduledView(APIView):
    """
        Returns the datetime of the last time new observations were submitted. This endpoint is expected to be polled
        frequently (~every 5 seconds) to for a client to decide if it needs to pull down the schedule or not.

        We are only updating when observations are submitted, and not when they are cancelled, because a site should
        not really care if the only change was removing things from it's schedule.
    """
    permission_classes = (IsAdminUser,)

    def get(self, request):
        site = request.query_params.get('site')
        cache_key = 'observation_portal_last_schedule_time'
        if site:
            cache_key += f"_{site}"
            last_schedule_time = cache.get(cache_key, timezone.now() - timedelta(days=7))
        else:
            sites = configdb.get_site_tuples()
            keys = [cache_key + "_" + s[0] for s in sites]
            cache_dict = cache.get_many(keys)
            last_schedule_time = max(list(cache_dict.values()) + [timezone.now() - timedelta(days=7)])

        return Response({'last_schedule_time': last_schedule_time})
