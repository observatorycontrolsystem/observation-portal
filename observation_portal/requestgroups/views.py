from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from django.views.generic.detail import DetailView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.schemas.openapi import AutoSchema
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.utils import timezone
from django.urls import reverse
from dateutil.parser import parse
from datetime import timedelta
from rest_framework.views import APIView
import logging

from observation_portal.common.configdb import configdb
from observation_portal.common.telescope_states import (
    TelescopeStates, get_telescope_availability_per_day, combine_telescope_availabilities_by_site_and_class,
    ElasticSearchException
)
from observation_portal.requestgroups.request_utils import get_airmasses_for_request_at_sites
from observation_portal.requestgroups.models import RequestGroup, Request
from observation_portal.requestgroups.serializers import RequestSerializer
from observation_portal.requestgroups.filters import RequestGroupFilter
from observation_portal.requestgroups.contention import Contention, Pressure

logger = logging.getLogger(__name__)


def get_start_end_parameters(request, default_days_back):
    try:
        start = parse(request.query_params.get('start'))
    except TypeError:
        start = timezone.now() - timedelta(days=default_days_back)
    start = start.replace(tzinfo=timezone.utc)
    try:
        end = parse(request.query_params.get('end'))
    except TypeError:
        end = timezone.now()
    end = end.replace(tzinfo=timezone.utc)
    return start, end


def requestgroup_queryset(request):
    if request.user.is_authenticated:
        if request.user.profile.staff_view and request.user.is_staff:
            requestgroups = RequestGroup.objects.all()
        else:
            requestgroups = RequestGroup.objects.filter(proposal__in=request.user.proposal_set.all())
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
                requests = Request.objects.filter(request_group__proposal__in=self.request.user.proposal_set.all())
                if self.request.user.profile.view_authored_requests_only:
                    requests = requests.filter(request_group__submitter=self.request.user)
        else:
            requests = Request.objects.filter(request_group__proposal__public=True)

        return requests


class RequestCreateView(LoginRequiredMixin, TemplateView):
    template_name = 'requestgroups/request_create.html'


class TelescopeStatesView(APIView):
    schema = AutoSchema(tags=['Utility API'])
    """
    Retrieves the telescope states for all telescopes between the start and end times
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            start, end = get_start_end_parameters(request, default_days_back=0)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        sites = request.query_params.getlist('site')
        telescopes = request.query_params.getlist('telescope')
        telescope_states = TelescopeStates(start, end, sites=sites, telescopes=telescopes).get()
        str_telescope_states = {str(k): v for k, v in telescope_states.items()}

        return Response(str_telescope_states)


class TelescopeAvailabilityView(APIView):
    """
    Retrieves the nightly percent availability of each telescope between the start and end times
    """
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            start, end = get_start_end_parameters(request, default_days_back=1)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        combine = request.query_params.get('combine')
        sites = request.query_params.getlist('site')
        telescopes = request.query_params.getlist('telescope')
        try:
            telescope_availability = get_telescope_availability_per_day(
                start, end, sites=sites, telescopes=telescopes
            )
        except ElasticSearchException:
            logger.warning('Error connecting to ElasticSearch. Is SBA reachable?')
            return Response('ConnectionError')
        if combine:
            telescope_availability = combine_telescope_availabilities_by_site_and_class(telescope_availability)
        str_telescope_availability = {str(k): v for k, v in telescope_availability.items()}

        return Response(str_telescope_availability)


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


class InstrumentsInformationView(APIView):
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request):
        info = {}
        is_staff = request.user.is_staff
        for instrument_type in configdb.get_instrument_types({}, only_schedulable=(not is_staff)):
            info[instrument_type] = {
                'type': 'SPECTRA' if configdb.is_spectrograph(instrument_type) else 'IMAGE',
                'class': configdb.get_instrument_type_telescope_class(instrument_type),
                'name': configdb.get_instrument_type_full_name(instrument_type),
                'optical_elements': configdb.get_optical_elements(instrument_type),
                'modes': configdb.get_modes_by_type(instrument_type),
                'default_acceptability_threshold': configdb.get_default_acceptability_threshold(instrument_type)
            }
        return Response(info)


class ContentionView(APIView):
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request, instrument_type):
        if request.user.is_staff:
            contention = Contention(instrument_type, anonymous=False)
        else:
            contention = Contention(instrument_type)
        return Response(contention.data())


class PressureView(APIView):
    schema = AutoSchema(tags=['Utility API'])
    permission_classes = (AllowAny,)

    def get(self, request):
        instrument_type = request.GET.get('instrument')
        site = request.GET.get('site')
        if request.user.is_staff:
            pressure = Pressure(instrument_type, site, anonymous=False)
        else:
            pressure = Pressure(instrument_type, site)
        return Response(pressure.data())


class ObservationPortalLastChangedView(APIView):
    '''
        Returns the datetime of the last status of requests change or new requests addition
    '''
    schema = AutoSchema(tags=['Requests API'])
    permission_classes = (IsAdminUser,)

    def get(self, request):
        last_change_time = cache.get('observation_portal_last_change_time', timezone.now() - timedelta(days=7))
        return Response({'last_change_time': last_change_time})
