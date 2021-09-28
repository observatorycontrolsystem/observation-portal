import os
import json

from rest_framework.management.commands.generateschema import Command as GenerateSchemaCommand
from django.conf import settings
import responses

CONFIGDB_DOC_FILE = os.path.join(settings.BASE_DIR, 'observation_portal/common/test_data/doc_configdb.json')


class Command(GenerateSchemaCommand):
    help = "Command to generate OpenAPI schema with external services mocked"
    def __init__(self):
        """Generate OpenAPI schema with mock ConfigDB data."""
        super().__init__()
        # Mock out ConfigDB response for doc generation.
        responses._default_mock.__enter__()
        responses.add(
            responses.GET, settings.CONFIGDB_URL + '/sites/', match_querystring=True,
            json=json.loads(open(CONFIGDB_DOC_FILE).read()), status=200
        )
