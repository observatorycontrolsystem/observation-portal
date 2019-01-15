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

from observation_portal.requestgroups.viewsets import RequestGroupViewSet, RequestViewSet
from observation_portal.requestgroups.views import TelescopeStatesView, TelescopeAvailabilityView, AirmassView
from observation_portal.requestgroups.views import InstrumentsInformationView, RequestGroupStatusIsDirty
from observation_portal.requestgroups.views import ContentionView, PressureView
from observation_portal.accounts.views import ProfileApiView

router = DefaultRouter()
router.register(r'requests', RequestViewSet, 'requests')
router.register(r'requestgroups', RequestGroupViewSet, 'request_groups')

api_urlpatterns = ([
    url(r'^', include(router.urls)),
    url(r'^api-token-auth/', obtain_auth_token, name='api-token-auth'),
    url(r'^telescope_states/', TelescopeStatesView.as_view(), name='telescope_states'),
    url(r'^telescope_availability/', TelescopeAvailabilityView.as_view(), name='telescope_availability'),
    url(r'profile/', ProfileApiView.as_view(), name='profile'),
    url(r'airmass/', AirmassView.as_view(), name='airmass'),
    url(r'instruments/', InstrumentsInformationView.as_view(), name='instruments_information'),
    url(r'isDirty/', RequestGroupStatusIsDirty.as_view(), name='isDirty'),
    url(r'contention/(?P<instrument_name>.+)/', ContentionView.as_view(), name='contention'),
    url(r'pressure/', PressureView.as_view(), name='pressure'),
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
    path('admin/', admin.site.urls),
    url(r'^api/', include(api_urlpatterns)),
    url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
