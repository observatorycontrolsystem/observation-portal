from django.core.exceptions import ValidationError
from django.core.cache import cache
from django_filters.rest_framework.backends import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from django.http import HttpResponseBadRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from dateutil.parser import parse
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework import status
import logging
from http import HTTPStatus

from observation_portal import settings
from observation_portal.common.configdb import configdb
from observation_portal.common.telescope_states import (
    TelescopeStates, get_telescope_availability_per_day, combine_telescope_availabilities_by_site_and_class,
    OpenSearchException
)
from observation_portal.requestgroups.request_utils import get_airmasses_for_request_at_sites
from observation_portal.requestgroups.contention import Contention, Pressure
from observation_portal.requestgroups.filters import InstrumentsInformationFilter, LastChangedFilter
from observation_portal.common.doc_examples import EXAMPLE_RESPONSES, QUERY_PARAMETERS
from observation_portal.common.schema import ObservationPortalSchema

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
    """Retrieves the telescope states for all telescopes between the start and end times
    """
    permission_classes = (AllowAny,)
    schema = None

    def get(self, request):
        try:
            start, end = get_start_end_parameters(request, default_days_back=0)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
        sites = request.query_params.getlist('site')
        telescopes = request.query_params.getlist('telescope')
        try:
            telescope_states = TelescopeStates(start, end, sites=sites, telescopes=telescopes, only_schedulable=False).get()
        except OpenSearchException:
            logger.warning('Error connecting to OpenSearch. Is the cluster reachable?')
            return Response('ConnectionError - Error retrieving telescope states', HTTPStatus.BAD_GATEWAY)

        str_telescope_states = {str(k): v for k, v in telescope_states.items()}

        return Response(str_telescope_states)


class TelescopeAvailabilityView(APIView):
    """Retrieves the nightly percent availability of each telescope between the start and end times
    """
    permission_classes = (AllowAny,)
    schema = None

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
        except OpenSearchException:
            logger.warning('Error connecting to OpenSearch. Is the cluster reachable?')
            return Response('ConnectionError - Error retrieving telescope availability', HTTPStatus.BAD_GATEWAY)
        if combine:
            telescope_availability = combine_telescope_availabilities_by_site_and_class(telescope_availability)
        str_telescope_availability = {str(k): v for k, v in telescope_availability.items()}

        return Response(str_telescope_availability)


class AirmassView(APIView):
    """Gets the airmasses for the request at available sites
    """
    permission_classes = (AllowAny,)
    schema = ObservationPortalSchema(tags=['Requests'])

    def post(self, request):
        request_serializer = self.get_request_serializer(data=request.data)
        if request_serializer.is_valid():
            airmass_data = get_airmasses_for_request_at_sites(request_serializer.validated_data, is_staff=request.user.is_staff)
            return Response(airmass_data)
        else:
            return Response(request_serializer.errors)

    def get_request_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['requestgroups']['Request'])(*args, **kwargs)

    def get_example_response(self):
        return Response(EXAMPLE_RESPONSES['requestgroups'].get('airmass'), status=status.HTTP_200_OK)

    def get_endpoint_name(self):
        return 'getAirmass'


class InstrumentsInformationView(APIView):
    """ Gets information about current instruments from the ConfigDB.
    """
    permission_classes = (AllowAny,)
    schema = ObservationPortalSchema(tags=['Utility'])
    filter_backends = (DjangoFilterBackend,)
    filterset_class = InstrumentsInformationFilter

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
        for instrument_type in configdb.get_instrument_type_codes(location=location, only_schedulable=only_schedulable):
            if not requested_instrument_type or requested_instrument_type.upper() == instrument_type.upper():
                ccd_size = configdb.get_ccd_size(instrument_type)
                info[instrument_type] = {
                    'type': configdb.get_instrument_type_category(instrument_type),
                    'class': configdb.get_instrument_type_telescope_class(instrument_type),
                    'name': configdb.get_instrument_type_full_name(instrument_type),
                    'optical_elements': configdb.get_optical_elements(instrument_type),
                    'modes': configdb.get_modes_by_type(instrument_type),
                    'default_acceptability_threshold': configdb.get_default_acceptability_threshold(instrument_type),
                    'configuration_types': configdb.get_configuration_types(instrument_type),
                    'default_configuration_type': configdb.get_default_configuration_type(instrument_type),
                    'camera_type': {
                        'science_field_of_view': configdb.get_diagonal_ccd_fov(instrument_type, autoguider=False),
                        'autoguider_field_of_view': configdb.get_diagonal_ccd_fov(instrument_type, autoguider=True),
                        'pixel_scale': configdb.get_pixel_scale(instrument_type),
                        'pixels_x': ccd_size['x'],
                        'pixels_y': ccd_size['y'],
                        'orientation': configdb.get_average_ccd_orientation(instrument_type)
                    }
                }
        return Response(info)

    def get_example_response(self):
        return Response(EXAMPLE_RESPONSES['requestgroups'].get('instruments'), status=status.HTTP_200_OK)

    def get_endpoint_name(self):
        return 'getInstruments'


class ContentionView(APIView):
    """Retrieve the contention for a given instrument type binned by RA hour. For every RA hour, the time currently requested
    on this instrument type for the next 24 hours is returned.
    """
    permission_classes = (AllowAny,)
    schema = ObservationPortalSchema(tags=['Utility'])

    def get(self, request, instrument_type):
        if request.user.is_staff:
            contention = Contention(instrument_type, anonymous=False)
        else:
            contention = Contention(instrument_type)
        return Response(contention.data())

    def get_example_response(self):
        return Response(data=EXAMPLE_RESPONSES['requestgroups']['contention'], status=status.HTTP_200_OK)

    def get_endpoint_name(self):
        return 'getContention'


class PressureView(APIView):
    """Retrieves the pressure for a given site and instrument for the next 24 hours, binned into 15-minute intervals. The pressure
    for an observation is defined as its length divided by the total length of time during which it is visible.
    """
    permission_classes = (AllowAny,)
    schema = ObservationPortalSchema(tags=['Utility'], is_list_view=False)

    def get(self, request):
        instrument_type = request.GET.get('instrument')
        site = request.GET.get('site')
        if request.user.is_staff:
            pressure = Pressure(instrument_type, site, anonymous=False)
        else:
            pressure = Pressure(instrument_type, site)
        return Response(pressure.data())

    def get_example_response(self):
        return Response(data=EXAMPLE_RESPONSES['requestgroups']['pressure'])

    def get_query_parameters(self):
        return QUERY_PARAMETERS['requestgroups']['pressure']

    def get_endpoint_name(self):
        return 'getPressure'


class ObservationPortalLastChangedView(APIView):
    """Returns the datetime of the last status of requests change or new requests addition
    """
    permission_classes = (IsAdminUser,)
    schema = ObservationPortalSchema(tags=['RequestGroups'], is_list_view=False)
    filterset_class = LastChangedFilter
    filter_backends = (DjangoFilterBackend,)

    def get(self, request):
        telescope_classes = request.GET.getlist('telescope_class', ['all'])
        most_recent_change_time = timezone.now() - timedelta(days=7)
        for telescope_class in telescope_classes:
            most_recent_change_time = max(most_recent_change_time, cache.get(f"observation_portal_last_change_time_{telescope_class}", timezone.now() - timedelta(days=7)))

        response_serializer = self.get_response_serializer(data={'last_change_time': most_recent_change_time})
        if response_serializer.is_valid():
            return Response(response_serializer.validated_data)
        else:
            raise ValidationError(response_serializer.errors)

    def get_response_serializer(self, *args, **kwargs):
        return import_string(settings.SERIALIZERS['requestgroups']['LastChanged'])(*args, **kwargs)

    def get_endpoint_name(self):
        return 'getLastChangedTime'
