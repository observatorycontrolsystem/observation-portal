from observation_portal.settings import *  # noqa
import logging
import os

# Settings specific to running tests. Using sqlite will run tests 100% in memory.
# https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/unit-tests/#using-another-settings-module
# This file should be automatically used during tests, but you can manually specify as well:
# ./manage.py --settings=observation_portal.test_settings

logging.disable(logging.CRITICAL)
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)
DEBUG = False
TEMPLATE_DEBUG = False

ORGANIZATION_NAME = 'Test Org'
ORGANIZATION_EMAIL = 'test@example.com'
ORGANIZATION_DDT_EMAIL = 'test@example.com'
ORGANIZATION_SUPPORT_EMAIL = 'test@example.com'
ORGANIZATION_ADMIN_EMAIL = 'test@example.com'

ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearchdevfake')
CONFIGDB_URL = os.getenv('CONFIGDB_URL', 'http://configdbfake')
DOWNTIMEDB_URL = os.getenv('DOWNTIMEDB_URL', 'http://downtimedbfake')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'unique-snowflake'
    },
    'locmem': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'locmem-cache'
    },
    'testlocmem': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-locmem-cache'
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
