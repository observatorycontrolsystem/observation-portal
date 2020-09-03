from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from django.http import HttpResponseBadRequest
from django.utils import timezone
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
from observation_portal.requestgroups.serializers import RequestSerializer
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


class TelescopeStatesView(APIView):
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
    permission_classes = (AllowAny,)

    def get(self, request):
        info = {}
        # Staff users by default should see all instruments, but can request only schedulable instruments.
        # Non-staff users are only allowed access to schedulable instruments.
        if request.user.is_staff:
            only_schedulable = request.query_params.get('only_schedulable', False)
        else:
            only_schedulable = True

        requested_instrument_type = request.query_params.get('instrument_type', '')
        location = {
            'site': request.query_params.get('site', ''),
            'enclosure': request.query_params.get('enclosure', ''),
            'telescope_class': request.query_params.get('telescope_class', ''),
            'telescope': request.query_params.get('telescope', ''),
        }
        for instrument_type in configdb.get_instrument_types(location=location, only_schedulable=only_schedulable):
            if not requested_instrument_type or requested_instrument_type.lower() == instrument_type.lower():
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
    permission_classes = (AllowAny,)

    def get(self, request, instrument_type):
        if request.user.is_staff:
            contention = Contention(instrument_type, anonymous=False)
        else:
            contention = Contention(instrument_type)
        return Response(contention.data())


class PressureView(APIView):
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
    permission_classes = (IsAdminUser,)

    def get(self, request):
        last_change_time = cache.get('observation_portal_last_change_time', timezone.now() - timedelta(days=7))
        return Response({'last_change_time': last_change_time})
