from django.conf.urls import url
from django.views.decorators.http import require_POST

from observation_portal.proposals.views import ProposalDetailView, ProposalListView, InviteCreateView
from observation_portal.proposals.views import MembershipDeleteView, SemesterAdminView, MembershipLimitView
from observation_portal.proposals.views import GlobalMembershipLimitView, SemesterDetailView, ProposalInviteDeleteView

app_name = 'proposals'
urlpatterns = [
    url(r'^membership/(?P<pk>.+)/delete/$', MembershipDeleteView.as_view(), name='membership-delete'),
    url(r'^membership/(?P<pk>.+)/limit/$', MembershipLimitView.as_view(), name='membership-limit'),
    url(r'^semester/(?P<pk>.+)/$', SemesterDetailView.as_view(), name='semester-detail'),
    url(r'^semesteradmin/(?P<pk>.+)/$', SemesterAdminView.as_view(), name='semester-admin'),
    url(r'^invitation/(?P<pk>.+)/delete/$', ProposalInviteDeleteView.as_view(), name='proposalinvite-delete'),
    url(r'^$', ProposalListView.as_view(), name='list'),
    url(r'^(?P<pk>.+)/invite/$', require_POST(InviteCreateView.as_view()), name='invite'),
    url(r'^(?P<pk>.+)/globallimit/$', require_POST(GlobalMembershipLimitView.as_view()), name='membership-global'),
    url(r'^(?P<pk>.+)/$', ProposalDetailView.as_view(), name='detail'),
]
