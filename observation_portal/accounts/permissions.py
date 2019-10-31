from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    """The request is either read-only, or the user is staff"""
    def has_permission(self, request, view):
        return bool(
            request.method in SAFE_METHODS
            or request.user and request.user.is_staff
        )


class IsDirectUser(BasePermission):
    """
    The user is a member of a proposal that allows direct submission. Users on
    proposals that allow direct submission have certain privileges.
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            direct_proposals = request.user.proposal_set.filter(direct_submission=True)
            return len(direct_proposals) > 0
        else:
            return False
