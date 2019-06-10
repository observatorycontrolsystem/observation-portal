from datetime import timedelta
import math

from django.utils import timezone

from observation_portal.requestgroups.models import Request
from observation_portal.common.rise_set_utils import (
    get_filtered_rise_set_intervals_by_site, get_site_rise_set_intervals
)
from observation_portal.common.configdb import configdb


class Contention(object):
    def __init__(self, instrument_type, anonymous=True):
        self.anonymous = anonymous
        self.now = timezone.now()
        self.instrument_type = instrument_type
        self.requests = self._requests(instrument_type)

    def _requests(self, instrument_type):
        return Request.objects.filter(
            windows__start__lt=self.now + timedelta(days=1),
            windows__end__gt=self.now,
            state='PENDING',
            configurations__instrument_type=instrument_type,
            configurations__target__type='ICRS'
        ).prefetch_related(
            'configurations', 'windows', 'configurations__target', 'location', 'request_group',
            'request_group__proposal', 'configurations__instrument_configs', 'configurations__acquisition_config',
            'configurations__guiding_config', 'configurations__constraints'
        ).distinct()

    def _binned_durations_by_proposal_and_ra(self):
        ra_bins = [{} for x in range(0, 24)]
        for request in self.requests:
            for conf in request.configurations.all():
                ra = math.floor(conf.target.ra / 15)
                proposal_id = request.request_group.proposal.id
                if not ra_bins[ra].get(proposal_id):
                    ra_bins[ra][proposal_id] = conf.duration
                else:
                    ra_bins[ra][proposal_id] += conf.duration
        return ra_bins

    @staticmethod
    def _anonymize(data):
        for index, ra in enumerate(data):
            data[index] = {'All Proposals': sum(ra.values())}
        return data

    def data(self):
        c_data = {
            'ra_hours': list(range(0, 24)),
            'instrument_type': self.instrument_type,
            'time_calculated': self.now
        }
        if self.anonymous:
            c_data['contention_data'] = self._anonymize(self._binned_durations_by_proposal_and_ra())
        else:
            c_data['contention_data'] = self._binned_durations_by_proposal_and_ra()
        return c_data


class Pressure(object):
    def __init__(self, instrument_type=None, site=None, anonymous=True):
        self.anonymous = anonymous
        self.now = timezone.now()
        self.requests = self._requests(instrument_type, site)
        self.site = site
        self.instrument_type = instrument_type
        self.sites = self._sites()
        self.telescopes = {}

    def _requests(self, instrument_type, site):
        requests = Request.objects.filter(
            windows__start__lte=self.now + timedelta(days=1),
            windows__end__gte=self.now,
            state='PENDING',
            configurations__target__type='ICRS'
        )
        if instrument_type:
            requests = requests.filter(configurations__instrument_type=instrument_type)

        return requests.prefetch_related(
            'configurations', 'windows', 'configurations__target', 'location', 'request_group', 'request_group__proposal',
            'configurations__instrument_configs', 'configurations__constraints', 'configurations__acquisition_config',
            'configurations__guiding_config'
        ).distinct()

    def _telescopes(self, instrument_type):
        if instrument_type not in self.telescopes:
            telescopes = configdb.get_telescopes_per_instrument_type(instrument_type, only_schedulable=True)
            self.telescopes[instrument_type] = telescopes
        return self.telescopes[instrument_type]

    def _sites(self):
        if self.site:
            return [{'code': self.site}]
        else:
            return configdb.get_site_data()

    def _site_nights(self):
        site_nights = {}
        for site in self.sites:
            site_nights[site['code']] = get_site_rise_set_intervals(
                self.now, self.now + timedelta(hours=24), site['code']
            )
        flattened = []
        for site in site_nights:
            for r, s in site_nights[site]:
                if s > self.now and r < self.now + timedelta(hours=24):
                    hours_until_rise = (max(self.now, r) - self.now).seconds / 3600
                    hours_until_set = min((s - self.now).days * 24 + (s - self.now).seconds / 3600, 24)
                    flattened.append(dict(
                        name=site,
                        start=hours_until_rise,
                        stop=hours_until_set
                    ))
        return flattened

    def _n_possible_telescopes(self, time, site_intervals, instrument_type):
        n_telescopes = 0
        for site in site_intervals:
            for interval in site_intervals[site]:
                if interval[0] <= time < interval[1]:
                    n_telescopes += sum([1 for t in self._telescopes(instrument_type) if t.site == site])
        return n_telescopes

    def _visible_intervals(self, request):
        visible_intervals = {}
        for site in self.sites:
            if not request.location.site or request.location.site == site['code']:
                intervals = get_filtered_rise_set_intervals_by_site(
                    request.as_dict(), site['code']
                ).get(site['code'], [])
                for r, s in intervals:
                    effective_rise = max(r, self.now)
                    if s > self.now and (s-effective_rise).seconds >= request.duration:
                        if site['code'] in visible_intervals:
                            visible_intervals[site['code']].append((effective_rise, s))
                        else:
                            visible_intervals[site['code']] = [(effective_rise, s)]
        return visible_intervals

    def _time_visible(self, site_intervals):
        return sum(sum((s - r).seconds for r, s in site_intervals[site]) for site in site_intervals)

    def _time_bins(self):
        return [self.now + timedelta(minutes=15 * x) for x in range(0, 24 * 4)]

    def _binned_pressure_by_hours_from_now(self):
        quarter_hour_bins = [{} for x in range(0, 24 * 4)]
        bin_start_times = self._time_bins()

        for request in self.requests:
            site_intervals = self._visible_intervals(request)
            total_time_visible = self._time_visible(site_intervals)
            instrument_type = request.configurations.all()[0].instrument_type

            if total_time_visible < 1:
                continue

            base_pressure = request.duration / total_time_visible
            for i, bin_start in enumerate(bin_start_times):
                n_telescopes = self._n_possible_telescopes(bin_start, site_intervals, instrument_type)

                if n_telescopes < 1:
                    continue

                pressure = base_pressure / n_telescopes
                proposal = request.request_group.proposal.id
                if not quarter_hour_bins[i].get(proposal):
                    quarter_hour_bins[i][proposal] = pressure
                else:
                    quarter_hour_bins[i][proposal] += pressure
        return quarter_hour_bins

    def _anonymize(self, data):
        for index, time in enumerate(data):
            data[index] = {'All Proposals': sum(time.values())}
        return data

    def data(self):
        p_data = {
            'site_nights': self._site_nights(),
            'time_bins': self._time_bins(),
            'instrument_type': self.instrument_type if self.instrument_type else 'all',
            'site': self.site if self.site else 'all',
            'time_calculated': self.now
        }
        if self.anonymous:
            p_data['pressure_data'] = self._anonymize(self._binned_pressure_by_hours_from_now())
        else:
            p_data['pressure_data'] = self._binned_pressure_by_hours_from_now()
        return p_data
