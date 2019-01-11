from django.conf.urls import url

from observation_portal.requestgroups.views import RequestGroupListView, RequestDetailView, RequestCreateView, \
    RequestGroupDetailView

app_name = 'requestgroups'
urlpatterns = [
    url(r'^$', RequestGroupListView.as_view(), name='list'),
    url(r'^requestgroups/(?P<pk>\d+)/$', RequestGroupDetailView.as_view(), name='detail'),
    url(r'^requests/(?P<pk>\d+)/$', RequestDetailView.as_view(), name='request-detail'),
    url(r'^create/$', RequestCreateView.as_view(), name='create')
]
