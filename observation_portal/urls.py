"""observation_portal URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf.urls.static import static

from observation_portal.requestgroups.viewsets import RequestGroupViewSet, RequestViewSet, DraftRequestGroupViewSet
from observation_portal.requestgroups.views import TelescopeStatesView, TelescopeAvailabilityView, AirmassView
from observation_portal.requestgroups.views import InstrumentsInformationView, ObservationPortalLastChangedView
from observation_portal.requestgroups.views import ContentionView, PressureView
from observation_portal.accounts.views import (
    ProfileApiView, RevokeApiTokenApiView, AccountRemovalRequestApiView, AcceptTermsApiView
)
from observation_portal.proposals.viewsets import (
    ProposalViewSet, SemesterViewSet, MembershipViewSet, ProposalInviteViewSet
)
from observation_portal.sciapplications.viewsets import CallViewSet, ScienceApplicationViewSet
from observation_portal.observations.views import LastScheduledView
from observation_portal.observations.viewsets import ObservationViewSet, ScheduleViewSet, ConfigurationStatusViewSet
import observation_portal.accounts.urls as accounts_urls
from observation_portal import settings

router = DefaultRouter()
router.register(r'requests', RequestViewSet, 'requests')
router.register(r'requestgroups', RequestGroupViewSet, 'request_groups')
router.register(r'drafts', DraftRequestGroupViewSet, 'drafts')
router.register(r'proposals', ProposalViewSet, 'proposals')
router.register(r'semesters', SemesterViewSet, 'semesters')
router.register(r'memberships', MembershipViewSet, 'memberships')
router.register(r'invitations', ProposalInviteViewSet, 'invitations')
router.register(r'calls', CallViewSet, 'calls')
router.register(r'scienceapplications', ScienceApplicationViewSet, 'scienceapplications')
router.register(r'observations', ObservationViewSet, 'observations')
router.register(r'schedule', ScheduleViewSet, 'schedule')
router.register(r'configurationstatus', ConfigurationStatusViewSet, 'configurationstatus')

api_urlpatterns = ([
    url(r'^', include(router.urls)),
    url(r'^api-token-auth/', obtain_auth_token, name='api-token-auth'),
    url(r'^telescope_states/', TelescopeStatesView.as_view(), name='telescope_states'),
    url(r'^telescope_availability/', TelescopeAvailabilityView.as_view(), name='telescope_availability'),
    url(r'profile/accept_terms/', AcceptTermsApiView.as_view(), name='accept_terms'),
    url(r'profile/', ProfileApiView.as_view(), name='profile'),
    url(r'revoke_token/', RevokeApiTokenApiView.as_view(), name='revoke_api_token'),
    url(r'account_removal_request/', AccountRemovalRequestApiView.as_view(), name='account_removal_request'),
    url(r'airmass/', AirmassView.as_view(), name='airmass'),
    url(r'instruments/', InstrumentsInformationView.as_view(), name='instruments_information'),
    url(r'contention/(?P<instrument_type>.+)/', ContentionView.as_view(), name='contention'),
    url(r'pressure/', PressureView.as_view(), name='pressure'),
    url(r'last_changed/', ObservationPortalLastChangedView.as_view(), name='last_changed'),
    url(r'last_scheduled/', LastScheduledView.as_view(), name='last_scheduled')
], 'api')

schema_view = get_schema_view(
   openapi.Info(
      title="Observation Portal API",
      default_version='v1',
      description="Test description",
      terms_of_service="https://lco.global/policies/terms/",
      contact=openapi.Contact(email="science-support@lco.global"),
      license=openapi.License(name="GPL 3.0 License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    url(r'^accounts/', include(accounts_urls)),
    url(r'^api/', include(api_urlpatterns)),
    url(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('admin/', admin.site.urls),
    url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
