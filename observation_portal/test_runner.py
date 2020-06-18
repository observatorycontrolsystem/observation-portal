from django.test.runner import DiscoverRunner
import responses
import json
import os
from django.conf import settings

CONFIGDB_TEST_FILE = os.path.join(settings.BASE_DIR, 'observation_portal/common/test_data/configdb.json')


class MyDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        responses._default_mock.__enter__()
        responses.add(
            responses.GET, settings.CONFIGDB_URL + '/sites/', match_querystring=True,
            json=json.loads(open(CONFIGDB_TEST_FILE).read()), status=200
        )

