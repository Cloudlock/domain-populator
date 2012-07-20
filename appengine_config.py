import os
import sys

from beaker.middleware import SessionMiddleware


def webapp_add_wsgi_middleware(app):

    session_opts = {
        'session.type': 'ext:google'
    }

    # add beaker middleware
    app = SessionMiddleware(app, session_opts)

    return app

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.2')
import django
