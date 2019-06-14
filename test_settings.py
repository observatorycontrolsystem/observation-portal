from observation_portal.settings import *  # noqa
import logging

# Settings specific to running tests. Using sqlite will run tests 100% in memory.
# https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/unit-tests/#using-another-settings-module
# This file should be automatically used during tests, but you can manually specify as well:
# ./manage.py --settings=valhalla.test_settings

logging.disable(logging.CRITICAL)
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)
DEBUG = False
TEMPLATE_DEBUG = False

ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearchdevfake.lco.gtn')
CONFIGDB_URL = os.getenv('CONFIGDB_URL', 'http://configdbfake.lco.gtn')
DOWNTIMEDB_URL = os.getenv('DOWNTIMEDB_URL', 'http://downtimedbfake.lco.gtn')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'unique-snowflake'
    },
    'locmem': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'locmem-cache'
    }
}

DRAMATIQ_BROKER = {
    "BROKER": "dramatiq.brokers.stub.StubBroker",
    "OPTIONS": {},
    "MIDDLEWARE": [
        "dramatiq.middleware.AgeLimit",
        "dramatiq.middleware.TimeLimit",
        "dramatiq.middleware.Callbacks",
        "dramatiq.middleware.Pipelines",
        "dramatiq.middleware.Retries",
        "django_dramatiq.middleware.DbConnectionsMiddleware",
    ]
}
