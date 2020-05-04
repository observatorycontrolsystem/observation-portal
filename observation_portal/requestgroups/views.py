from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from django.views.generic.detail import DetailView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.schemas.openapi import AutoSchema
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from rest_framework.views import APIView
import logging

from observation_portal.common.mixins import GetSerializerMixin, RetrieveMixin
from observation_portal.common.telescope_states import ElasticSearchException
from observation_portal.requestgroups.request_utils import get_airmasses_for_request_at_sites
from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.requestgroups.schema_serializers import (TelescopeStatesSerializer, InstrumentsInfoSerializer,
                                                                 TelescopesAvailabilitySerializer, ContentionSerializer,
                                                                 PressureSerializer)
from observation_portal.requestgroups.serializers import RequestSerializer
from observation_portal.requestgroups.filters import (
    RequestGroupFilter, TelescopeStatesFilter, TelescopeAvailabilityFilter, PressureFilter)

logger = logging.getLogger(__name__)


def requestgroup_queryset(request):
    if request.user.is_authenticated:
        if request.user.profile.staff_view and request.user.is_staff:
            requestgroups = RequestGroup.objects.all()
        else:
            requestgroups = RequestGroup.objects.filter(
                proposal__in=request.user.proposal_set.all())
            if request.user.profile.view_authored_requests_only:
                requestgroups = requestgroups.filter(submitter=request.user)
    else:
        requestgroups = RequestGroup.objects.filter(proposal__public=True)

    return requestgroups


class RequestGroupListView(FilterView):
    filterset_class = RequestGroupFilter
    template_name = 'requestgroups/requestgroup_list.html'
    strict = False  # TODO remove when https://github.com/carltongibson/django-filter/issues/930 is fixed

    def get_queryset(self):
        return requestgroup_queryset(self.request)

    def get_paginate_by(self, qs):
        return self.request.GET.get('paginate_by', 20)


class RequestGroupDetailView(DetailView):
    model = RequestGroup

    def get_queryset(self):
        return requestgroup_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests = self.get_object().requests.all().order_by('id')
        paginator = Paginator(requests, 25)
        page = self.request.GET.get('page')
        try:
            requests = paginator.page(page)
        except PageNotAnInteger:
            requests = paginator.page(1)
        except EmptyPage:
            requests = paginator.page(paginator.num_pages)
        context['requests'] = requests

        return context

    def render_to_response(self, context, **kwargs):
        if self.get_object().requests.count() == 1:
            request = self.get_object().requests.first()
            return HttpResponseRedirect(reverse('requestgroups:request-detail', args=(request.id, )))
        else:
            return super().render_to_response(context, **kwargs)


class RequestDetailView(DetailView):
    model = Request

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.profile.staff_view and self.request.user.is_staff:
                requests = Request.objects.all()
            else:
                requests = Request.objects.filter(
                    request_group__proposal__in=self.request.user.proposal_set.all())
                if self.request.user.profile.view_authored_requests_only:
                    requests = requests.filter(
                        request_group__submitter=self.request.user)
        else:
            requests = Request.objects.filter(
                request_group__proposal__public=True)

        return requests


class RequestCreateView(LoginRequiredMixin, TemplateView):
    template_name = 'requestgroups/request_create.html'


class TelescopeStatesView(RetrieveMixin, APIView, GetSerializerMixin):
    """
    Retrieves the telescope states for all telescopes between the start and end times
    """
    filter_class = TelescopeStatesFilter
    filter_backends = (
        DjangoFilterBackend,
    )
    serializer_class = TelescopeStatesSerializer
    schema = AutoSchema(tags=['Utility API'], component_name='TelescopeStates', operation_id_base='TelescopeStates')
    permission_classes = (AllowAny,)

    def get(self, request):
        ser = TelescopeStatesSerializer(data=request.query_params)
        if ser.is_valid(raise_exception=True):
            return Response(ser.data)


class TelescopeAvailabilityView(RetrieveMixin, APIView, GetSerializerMixin):
    """
    Retrieves the nightly percent availability of each telescope between the start and end times.
    The optional `combine` parameter will combine all telescopes of the same type together at each site.
    """
    serializer_class = TelescopesAvailabilitySerializer
    filter_class = TelescopeAvailabilityFilter
    filter_backends = (
        DjangoFilterBackend,
    )
    schema = AutoSchema(tags=['Utility API'], component_name='TelescopeAvailability', operation_id_base='TelescopeAvailability')
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            ser = TelescopesAvailabilitySerializer(data=request.query_params)
            if ser.is_valid(raise_exception=True):
                return Response(ser.data)
        except ElasticSearchException:
            logger.warning(
                'Error connecting to ElasticSearch. Is SBA reachable?')
            return Response('ConnectionError')


class AirmassView(APIView):
    """
    Gets the airmasses for the request at available sites
    """
    schema = AutoSchema(tags=['Requests API'])
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = RequestSerializer(data=request.data)
        if serializer.is_valid():
            return Response(get_airmasses_for_request_at_sites(
                serializer.validated_data, is_staff=request.user.is_staff
            ))
        else:
            return Response(serializer.errors)


class InstrumentsInformationView(RetrieveMixin, APIView, GetSerializerMixin):
    """
    Gets information on instruments this user has time on
    """
    schema = AutoSchema(tags=['Utility API'], component_name='InstrumentInformation', operation_id_base='Instruments')
    permission_classes = (AllowAny,)
    serializer_class = InstrumentsInfoSerializer

    def get(self, request):
        ser = InstrumentsInfoSerializer(data={'is_staff': request.user.is_staff})
        if ser.is_valid(raise_exception=True):
            return Response(ser.data)


class ContentionView(RetrieveMixin, APIView, GetSerializerMixin):
    """
    Gets the contention on the network as a function of ra hour for an `instrument_type`. The `ra_hours` and 
    `contention_data` lists will be the same length of 24. The `instrument_type` can be "all" to combine all instruments.
    """
    serializer_class = ContentionSerializer
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request, instrument_type):
        ser = ContentionSerializer(data={'instrument_type': instrument_type, 'is_staff': request.user.is_staff})
        if ser.is_valid(raise_exception=True):
            return Response(ser.data)


class PressureView(RetrieveMixin, APIView, GetSerializerMixin):
    """
    Gets the pressure in the next 24 hours for a given `site` and `instrument` type.
    The `time_bins` and `pressure_data` lists will be the same length and correspond to each other.
    """
    serializer_class = PressureSerializer
    filter_class = PressureFilter
    filter_backends = (
        DjangoFilterBackend,
    )
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request):
        ser = PressureSerializer(data={'instrument_type': request.GET.get('instrument'),
                                       'site': request.GET.get('site'),
                                       'is_staff': request.user.is_staff})
        if ser.is_valid(raise_exception=True):
            return Response(ser.data)


class ObservationPortalLastChangedView(APIView):
    '''
        Returns the datetime of the last status of requests change or new requests addition
    '''
    schema = AutoSchema(tags=['Requests API'])
    permission_classes = (IsAdminUser,)

    def get(self, request):
        last_change_time = cache.get(
            'observation_portal_last_change_time', timezone.now() - timedelta(days=7))
        return Response({'last_change_time': last_change_time})
