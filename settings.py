# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Django settings for google-app-engine-django project.

import os, datetime

DEBUG = True
TEMPLATE_DEBUG = DEBUG

RUNNING_IN_PRODUCTION = os.environ.get('SERVER_SOFTWARE','').startswith('Google App Engine')
FORCE_SSL_MIDDLEWARE_ENABLED = RUNNING_IN_PRODUCTION


ADMINS = (
    # ('Your Name', 'your_email@domain.com'),
)

MANAGERS = ADMINS

DATABASE_ENGINE = 'appengine'  # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
DATABASE_NAME = ''             # Or path to database file if using sqlite3.
DATABASE_USER = ''             # Not used with sqlite3.
DATABASE_PASSWORD = ''         # Not used with sqlite3.
DATABASE_HOST = ''             # Set to empty string for localhost. Not used with sqlite3.
DATABASE_PORT = ''             # Set to empty string for default. Not used with sqlite3.

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'UTC'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'hvhxfm5u=^*v&doo#oq8x*eg8+1&9sxbye@=umutgn^t_sg_nx'

# Ensure that email is not sent via SMTP by default to match the standard App
# Engine SDK behaviour. If you want to sent email via SMTP then add the name of
# your mailserver here.
EMAIL_HOST = ''

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
#     'django.template.loaders.eggs.load_template_source',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',

    'admin.middleware.CatchSpuriousErrors',
    'admin.middleware.ForceSSL',

#    'django.contrib.sessions.middleware.SessionMiddleware',
#    'django.contrib.auth.middleware.AuthenticationMiddleware',
#    'django.middleware.doc.XViewMiddleware',
)

TEMPLATE_CONTEXT_PROCESSORS = (
#   'django.core.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
#    'django.core.context_processors.media',  # 0.97 only.
    'django.core.context_processors.request',
)

ROOT_URLCONF = 'urls'

ROOT_PATH = os.path.dirname(__file__)
TEMPLATE_DIRS = (
    os.path.join(ROOT_PATH, 'templates')
)

# get my host name
port = os.environ.get('SERVER_PORT', None)
server_name = os.environ.get('SERVER_NAME', "localhost")

if port and port != '80':
    HOST_NAME = '%s:%s' % (server_name, port)
else:
    HOST_NAME = server_name

INSTALLED_APPS = (
     'appengine_django',
#    'django.contrib.auth',
#    'django.contrib.contenttypes',
#    'django.contrib.sessions',
#    'django.contrib.sites',
     'admin',
     'gdocsaudit',
     'gapps',
     'marketplace',
)

COOKIE_DOMAIN=None

API_CLIENT_SOURCE = 'Aprigo-CloudLock-1'

if RUNNING_IN_PRODUCTION:
    DEBUG_AS_THIS_USER = None
    DEBUG_WITH_ALL_USERS = None
    DEBUG_ALL_USERS_HAVE_ZERO_DOCS = False

else:
    # Fill in the below to test as the given user.
    # Do not under any circumstances deploy this in production
    DEBUG_AS_THIS_USER = None # dict(nickname="", email="")

    # Provide a list here if you want to only use a subset of users
    DEBUG_WITH_ALL_USERS = None

    #TEST_RESULTS_EMAIL_ON_PASS = TEST_RESULTS_EMAIL_ON_FAIL = [ "shimonrura@gmail.com" ]
    TEST_RESULTS_EMAIL_ON_PASS = TEST_RESULTS_EMAIL_ON_FAIL = [ "matt@cloudlock.com" ]
    #DEBUG_AS_THIS_USER = dict(nickname="Ron Z", email="ron@aprigo.com")
    #DEBUG_WITH_ALL_USERS = [ "nathan", "mike" ]
    DEBUG_ALL_USERS_HAVE_ZERO_DOCS = False

    import logging
    logging.basicConfig(
        level = logging.DEBUG,
        format = '%(asctime)s %(levelname)s %(message)s')

# for dev listing:
#GAPPS_CONSUMER_KEY = "270868241771.apps.googleusercontent.com"
#GAPPS_CONSUMER_SECRET="uLbTOfEEx8bxrpq4nUjPxaVU"

# for aprigocloudlock:
GAPPS_CONSUMER_KEY = "364307572168.apps.googleusercontent.com"
GAPPS_CONSUMER_SECRET="vdTkALAq8OVZ6jRrx_CVEk3c"

# for production listing:
#GAPPS_CONSUMER_KEY = "784351852962.apps.googleusercontent.com"
#GAPPS_CONSUMER_SECRET="17I3cDwDgl7ENN-pYObA7IW4"

# what is the link on the marketplace to install this app?
##MKT_INSTALL_PREFIX = "https://www.google.com/enterprise/marketplace/redirectWithSignature?url=https://www.google.com/a/cpanel/"

# domain - for dev listing:
# MKT_INSTALL_SUFFIX = "/DomainAppInstall?appId%3D687057800104%26vendorId%3D11483%26productConfigId%3D7823%26productListingId%3D4511%2B12043259153010515087"
# MKT_LISTING_URL = "https://www.google.com/enterprise/marketplace/viewListing?productListingId=4511+12043259153010515087"

# domain - for prod listing:
##MKT_INSTALL_SUFFIX = "/DomainAppInstall?appId%3D364307572168%26vendorId%3D16009%26productConfigId%3D11806%26productListingId%3D5649%2B9637511031539972110"
##MKT_LISTING_URL = "https://www.google.com/enterprise/marketplace/viewListing?productListingId=5649+9637511031539972110"

# used in manifest generation
DEPLOYED_URL = "https://aprigoninja8.appspot.com"
OPENID_REALM = DEPLOYED_URL

# Treat requests from IPs starting with the below as privileged task queue
# or cron activity.
AE_TASK_IP_PREFIX = "0.1."


DEBUG_AS_THIS_USER = None

# This must be AT LEAST ONE under the limit for tasks queued within a
# transaction. That limit is 5, so this must be no more than 4.
# http://code.google.com/appengine/docs/python/taskqueue/overview.html#Task_Within_Transactions
NUM_USERPROCS_TO_ENQUEUE_PER_NIBBLE = 4 # was 10

# @taskqueue_only decorator gives up after this many retries.
# ALL FAILURE LIMITS BELOW MUST BE LESS THAN THIS
MAX_TASKQUEUE_FAILURES = 20

# if calls to docs API fail at least this many times, give up on the user
MAX_API_FAILURES_PER_USER = 10

# If dbupdates are failing, how many (consecutive) retries to allow? Should
# be enough to overcome a few transaction collisions, but not enough to
# stall the report if there's something about the data preventing it from
# being commitable.
MAX_DBUPDATE_FAILURES = 12

# task_domain_user_chunk retry limit
MAX_USER_CHUNK_FAILURES = 10

# task_domain_user_scan retry limit
MAX_DOMAIN_CRAWL_FAILURES = 10

# ### replace the above with:
# MAX_CONSECUTIVE_API_FAILURES_PER_USER = 10
# MAX_TOTAL_API_FAILURES_PER_USER = 100

# How long to spend fetching user list during initial start of report.
MAX_INITIAL_USER_LOAD_SECONDS = 1.0
MAX_TASK_USER_LOAD_SECONDS = 10.0

# Up to this many users per DomainUserCrawlChunk should be in the 'processing' state.
ACTIVE_USERS_PER_CHUNK_THROTTLE = 10

# If started longer than this ago, ignore scan marker and rescan.
STUCK_USER_RESCAN_TIME = datetime.timedelta(days=0, seconds=(3600*8))

QUEUE_SUFFIXES = ['-000','-001','-002','-003','-004','-005','-006','-007','-008','-009','-010']

# What is the default feature level and account expiration delay?
DEFAULT_FEATURE_LEVEL = "free"
DEFAULT_EXPIRATION_DELAY = datetime.timedelta(days=7)

HTTP_REQUEST_DEADLINE = 100 # 10 is the max

# From address for server errors, must be an app admin
SERVER_EMAIL = "gdocs@cloudlock.com"
