from django.conf.urls import url

from observation_portal.sciapplications.views import (
    SciApplicationCreateView, SciApplicationUpdateView, SciApplicationIndexView,
    SciApplicationDetailView, SciApplicationDeleteView, SciApplicationPDFView
)

app_name = 'sciapplications'
urlpatterns = [
    url(r'^$', SciApplicationIndexView.as_view(), name='index'),
    url(r'^(?P<pk>\d+)/$', SciApplicationDetailView.as_view(), name='detail'),
    url(r'^(?P<pk>\d+)/combined_pdf/$', SciApplicationPDFView.as_view(), name='pdf'),
    url(r'^create/(?P<call>\d+)/$', SciApplicationCreateView.as_view(), name='create'),
    url(r'^update/(?P<pk>\d+)/$', SciApplicationUpdateView.as_view(), name='update'),
    url(r'^delete/(?P<pk>\d+)/$', SciApplicationDeleteView.as_view(), name='delete'),

]
