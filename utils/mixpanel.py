import base64
from django.conf import settings
from django.utils import simplejson
from google.appengine.api import urlfetch


def track(event, properties=None):
    """
    Asynchronously log to the mixpanel.com API on App Engine.

    :param event: The overall event/category you would like to log this data under
    :param properties: A dictionary of key-value pairs that describe the event
        See http://mixpanel.com/api/ for further detail.
    :return: Instance of RPC Object
    """
    if properties == None:
        properties = {}
    if 'token' not in properties:
        properties['token'] = settings.MIXPANEL_TOKEN

    params = {'event': event, 'properties': properties}

    data = base64.b64encode(simplejson.dumps(params))
    request =  settings.MIXPANEL_API + '?data=' + data

    rpc = urlfetch.create_rpc()
    urlfetch.make_fetch_call(rpc, request)

    # Dev appserver doesn't work with rpc :-/
    if not settings.RUNNING_IN_PRODUCTION:
        rpc.wait()

    return rpc

def track_funnel(funnel, step, goal, properties=None):
    """
    Helper function for setting up funnel properties for use with track()
    """
    if properties == None:
        properties = {}
    properties['funnel'] = funnel
    properties['step'] = step
    properties['goal'] = goal
    track('mp_funnel', properties)


