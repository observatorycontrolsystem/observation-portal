from rest_framework.throttling import UserRateThrottle


class AllowStaffUserRateThrottle(UserRateThrottle):
    def get_cache_key(self, request, view):
        if request.user.is_staff:
            return None
        else:
            return super().get_cache_key(request, view)
