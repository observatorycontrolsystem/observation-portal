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
from django.urls import re_path, include, path
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework import permissions
from drf_yasg import openapi
from rest_framework.schemas import get_schema_view
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf.urls.static import static
from django.views.generic import TemplateView

from observation_portal.requestgroups.viewsets import RequestGroupViewSet, RequestViewSet, DraftRequestGroupViewSet, ConfigurationViewSet
from observation_portal.requestgroups.views import TelescopeStatesView, TelescopeAvailabilityView, AirmassView
from observation_portal.requestgroups.views import InstrumentsInformationView, ObservationPortalLastChangedView
from observation_portal.requestgroups.views import ContentionView, PressureView
from observation_portal.accounts.views import (
    ProfileApiView, RevokeApiTokenApiView, AccountRemovalRequestApiView,
    AcceptTermsApiView, BulkCreateUsersApiView
)
from observation_portal.proposals.viewsets import (
    ProposalViewSet, SemesterViewSet, MembershipViewSet, ProposalInviteViewSet
)
from observation_portal.sciapplications.viewsets import (
    CallViewSet,
    ScienceApplicationViewSet,
    ScienceApplicationReviewViewSet,
    ScienceApplicationReviewSummaryViewSet,
    ScienceApplicationReviewSecondaryNotesViewSet,
    ScienceApplicationMyReviewViewSet,
    ScienceApplicationUserReviewViewSet,
)
from observation_portal.observations.views import LastScheduledView
from observation_portal.observations.viewsets import ObservationViewSet, ScheduleViewSet, RealTimeViewSet, ConfigurationStatusViewSet
import observation_portal.accounts.urls as accounts_urls
from observation_portal import settings
from observation_portal.common.schema import ObservationPortalSchemaGenerator

router = DefaultRouter()
router.register(r'requests', RequestViewSet, 'requests')
router.register(r'requestgroups', RequestGroupViewSet, 'request_groups')
router.register(r'configurations', ConfigurationViewSet, 'configurations')
router.register(r'drafts', DraftRequestGroupViewSet, 'drafts')
router.register(r'proposals', ProposalViewSet, 'proposals')
router.register(r'semesters', SemesterViewSet, 'semesters')
router.register(r'memberships', MembershipViewSet, 'memberships')
router.register(r'invitations', ProposalInviteViewSet, 'invitations')
router.register(r'calls', CallViewSet, 'calls')
router.register(r'scienceapplications', ScienceApplicationViewSet, 'scienceapplications')
router.register(r'scienceapplication-reviews', ScienceApplicationReviewViewSet, 'scienceapplication-reviews')
router.register(r'scienceapplication-user-reviews', ScienceApplicationUserReviewViewSet, 'scienceapplication-user-reviews')
router.register(r'observations', ObservationViewSet, 'observations')
router.register(r'schedule', ScheduleViewSet, 'schedule')
router.register(r'realtime', RealTimeViewSet, 'realtime')
router.register(r'configurationstatus', ConfigurationStatusViewSet, 'configurationstatus')

api_urlpatterns = ([
    re_path(r'^', include(router.urls)),
    re_path(r'^api-token-auth/', obtain_auth_token, name='api-token-auth'),
    path('users-bulk/', BulkCreateUsersApiView.as_view(), name='users-bulk'),
    path(
        'scienceapplication-reviews/<int:pk>/summary',
        ScienceApplicationReviewSummaryViewSet.as_view({"get": "retrieve", "put": "update"}),
        name="scienceapplication-review-summary"
    ),
    path(
        "scienceapplication-reviews/<int:pk>/secondary-notes",
        ScienceApplicationReviewSecondaryNotesViewSet.as_view({"get": "retrieve", "put": "update"}),
        name="scienceapplication-review-secondary-notes"
    ),
    path(
        'scienceapplication-reviews/<int:pk>/my-review',
        ScienceApplicationMyReviewViewSet.as_view({"post": "create", "get": "retrieve", "put": "update", "patch": "partial_update"}),
        name="scienceapplication-my-review"
    ),
    re_path(r'^telescope_states/', TelescopeStatesView.as_view(), name='telescope_states'),
    re_path(r'^telescope_availability/', TelescopeAvailabilityView.as_view(), name='telescope_availability'),
    re_path(r'profile/accept_terms/', AcceptTermsApiView.as_view(), name='accept_terms'),
    re_path(r'profile/', ProfileApiView.as_view(), name='profile'),
    re_path(r'revoke_token/', RevokeApiTokenApiView.as_view(), name='revoke_api_token'),
    re_path(r'account_removal_request/', AccountRemovalRequestApiView.as_view(), name='account_removal_request'),
    re_path(r'airmass/', AirmassView.as_view(), name='airmass'),
    re_path(r'instruments/', InstrumentsInformationView.as_view(), name='instruments_information'),
    re_path(r'contention/(?P<instrument_type>.+)/', ContentionView.as_view(), name='contention'),
    re_path(r'pressure/', PressureView.as_view(), name='pressure'),
    re_path(r'last_changed/', ObservationPortalLastChangedView.as_view(), name='last_changed'),
    re_path(r'last_scheduled/', LastScheduledView.as_view(), name='last_scheduled')
], 'api')

schema_view = get_schema_view(
  openapi.Info(
    title="Observation Portal API",
    default_version='v1',
    terms_of_service="https://lco.global/policies/terms/",
    contact=openapi.Contact(email="ocs@lco.global"),
    license=openapi.License(name="GPL 3.0 License"),
  ),
  permission_classes=(permissions.AllowAny,),
  generator_class=ObservationPortalSchemaGenerator,
  public=True,
)

urlpatterns = [
    path("zpages/health/", include("health_check.urls")),
    re_path(r'^accounts/', include(accounts_urls)),
    re_path(r'^api/', include(api_urlpatterns)),
    re_path(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('admin/', admin.site.urls),
    path('openapi/', schema_view, name='openapi-schema'),
    path('redoc/', TemplateView.as_view(
        template_name='redoc.html',
        extra_context={'schema_url':'openapi-schema'}
    ), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
