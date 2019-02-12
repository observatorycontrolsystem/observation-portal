import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# TODO: This whole file will change since the pond stuff is moving into the observation portal


def split_time(start, end, chunks=4):
    chunk = (end - start) / chunks
    spans = [(start, start + chunk)]
    for i in range(0, chunks - 1):
        spans.append((spans[i][1], spans[i][1] + chunk))
    return spans


def get_time_totals_from_pond(timeallocation, start, end, too, recur=0):
    """
    Pond queries are too slow with large proposals and time out, this hack splits the query
    when a timeout occurs
    """
    if recur > 3:
        raise RecursionError('Pond is timing out, too much recursion.')

    total = 0
    try:
        total += query_pond(
            timeallocation.proposal.id, start, end, timeallocation.instrument_type, too
        )
    except requests.HTTPError:
        logger.warning('We got a pond inception. Splitting further.')
        for start, end in split_time(start, end, 4):
            total += get_time_totals_from_pond(timeallocation, start, end, too, recur=recur + 1)

    return total


def query_pond(proposal_id, start, end, instrument_class, too):
    logger.info('Attempting to get time used for %s from %s to %s', proposal_id, start, end)
    time_type = 'RAPID_RESPONSE' if too else 'NORMAL'
    start = start.strftime('%Y-%m-%dT%H:%M:%S.%f')
    end = end.strftime('%Y-%m-%dT%H:%M:%S.%f')
    url = '{0}/accounting/{1}/?proposal_id={2}&start={3}&end={4}&instrument_class={5}'.format(
        'http://lake.lco.gtn', time_type, proposal_id, start, end, instrument_class
    )
    response = requests.get(url)
    response.raise_for_status()
    if too:
        return response.json()['block_bounded_attempted_hours']
    else:
        return response.json()['attempted_hours']
