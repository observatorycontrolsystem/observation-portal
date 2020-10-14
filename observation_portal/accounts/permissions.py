from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAuthenticated

from observation_portal.proposals.models import Membership, ProposalInvite


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


class IsPrincipleInvestigator(IsAuthenticated):
    """The user is the principle investigator of the associated object"""
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_authenticated:
            if isinstance(obj, Membership):
                proposal = obj.proposal
            elif isinstance(obj, ProposalInvite):
                proposal = obj.proposal
            else:
                proposal = obj
            return request.user.membership_set.filter(proposal=proposal, role=Membership.PI).exists()
        else:
            return False
