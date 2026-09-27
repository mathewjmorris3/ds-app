"""PostgreSQL verification using an explicit disposable database and test role.

Never load deployment credentials here. Provision the database separately, then
run tests with --keepdb so Django neither creates nor drops a database.
"""
import os
from django.core.exceptions import ImproperlyConfigured
from .test_settings import *  # noqa: F403

name = os.environ.get('DSAPP_TEST_DB', '')
user = os.environ.get('DSAPP_TEST_USER', '')
if not name.startswith('dsapp_test_') or not user.startswith('dsapp_test_'):
    raise ImproperlyConfigured('Use dedicated dsapp_test_ database and role names.')
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': name,
    'USER': user,
    'PASSWORD': os.environ['DSAPP_TEST_PASSWORD'],
    'HOST': os.environ.get('DSAPP_TEST_HOST', '127.0.0.1'),
    'PORT': os.environ.get('DSAPP_TEST_PORT', '5432'),
    'TEST': {'NAME': name},
}}
