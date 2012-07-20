#gdocsaudit.tools
import logging
import time
import re
import gdata.auth
import gdata.alt.appengine
import gdata.docs
import gdata.docs.service
import gdata.docs.client
import gdata.sites.client
import gdata.apps.migration.service
import gdata.apps.adminsettings.service
from gdata.apps.service import AppsForYourDomainException
from django.http import HttpResponse, Http404, HttpResponseRedirect

from django.conf import settings
from google.appengine.ext import db

from google.appengine.api.urlfetch import ResponseTooLargeError, DownloadError


import gdata.service

INIT = {
    'APP_NAME': settings.API_CLIENT_SOURCE,
    'SCOPES': ['https://apps-apis.google.com/a/feeds/']
    }

def _client_setup_common(client, domain):
    client.ssl = True
    client.domain = domain
    client.source = settings.API_CLIENT_SOURCE

    # Use the maximum deadline (timeout) for slow-ass GData API calls.
    # Currently the max allowed is 10 seconds.
    #gdata.alt.appengine.run_on_appengine(client, deadline=settings.HTTP_REQUEST_DEADLINE)

def get_docs_client(requestor_id, domain):
    client = gdata.docs.client.DocsClient()
    two_legged_oauth_token = gdata.gauth.TwoLeggedOAuthHmacToken(
        settings.GAPPS_CONSUMER_KEY, 
        settings.GAPPS_CONSUMER_SECRET, 
        requestor_id)

    client.auth_token = two_legged_oauth_token
    _client_setup_common(client, domain)
    return client


def get_gapps_client(requestor_id, domain, svc="docs"):
    """
    Get a client object for the given domain. Possible svc values:

    'docs' - gets a gdata.docs.service.DocsService object (GDocs API v2)
    'docsclient' - gdata.docs.client.DocsClient (GDocs API v3; preferred)
    'prov' - gdata.apps.migration.service.MigrationService (provisioning API)
    'sites' - gdata.sites.client.SitesClient (Sites API)
    """

    if svc == "docs":
        Svc = gdata.docs.service.DocsService
    elif svc == "docsclient":
        #Svc = gdata.docs.client.DocsClient
        return get_docs_client(requestor_id, domain)
    elif svc == "prov":
        Svc = gdata.apps.migration.service.MigrationService
    elif svc == "sites":
        Svc = gdata.sites.client.SitesClient
    elif svc == "groups":
        Svc = gdata.apps.groups.service.GroupsService
    elif svc == 'organization':
        Svc = OrganizationService

    client = Svc()#additional_headers={gdata.contacts.service.GDATA_VER_HEADER: 3})

    SIG_METHOD = gdata.auth.OAuthSignatureMethod.HMAC_SHA1


    if svc == "docs":
        client.SetOAuthInputParameters(
            SIG_METHOD, 
            settings.GAPPS_CONSUMER_KEY, 
            consumer_secret=settings.GAPPS_CONSUMER_SECRET,
            two_legged_oauth=True, 
            requestor_id=requestor_id)

    elif svc in ("docsclient", "sites"):
        two_legged_oauth_token = gdata.gauth.TwoLeggedOAuthHmacToken(
            settings.GAPPS_CONSUMER_KEY, 
            settings.GAPPS_CONSUMER_SECRET, 
            requestor_id)

        client.auth_token = two_legged_oauth_token

    elif svc == "prov" or svc == "groups":
        client.SetOAuthInputParameters(
            SIG_METHOD, 
            settings.GAPPS_CONSUMER_KEY, 
            consumer_secret=settings.GAPPS_CONSUMER_SECRET,
            two_legged_oauth=True)
            #requestor_id=requestor_id) # see http://www.google.com/support/forum/p/apps-apis/thread?tid=04e57fd2cfdc4bdd&hl=en

    elif svc == "organization":
        email = requestor_id
        password = "Apr1g0Lab"
        client = OrganizationService(email=email, domain=domain, password=password)
        client.ProgrammaticLogin()

    client.ssl = True
    client.domain = domain
    client.source = settings.API_CLIENT_SOURCE

    # Use the maximum deadline (timeout) for slow-ass GData API calls.
    # Currently the max allowed is 10 seconds.
    #gdata.alt.appengine.run_on_appengine(client, deadline=settings.HTTP_REQUEST_DEADLINE)

    return client

def get_oauth_client(uri):

    INIT = {
    'APP_NAME': settings.API_CLIENT_SOURCE,
    'SCOPES': ['https://apps-apis.google.com/a/feeds/']
    }

    consumer_key = settings.GAPPS_CONSUMER_KEY
    consumer_secret = settings.GAPPS_CONSUMER_SECRET
    gd_client = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE)

    """Demonstrates usage of OAuth authentication mode and retrieves a list of
    documents using Document List Data API."""
    logging.info('STEP 1: Set OAuth input parameters.')
    gd_client.SetOAuthInputParameters(
        gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
        consumer_key, consumer_secret=consumer_secret)
    logging.info('STEP 2: Fetch OAuth Request token.')
    request_token = gd_client.FetchOAuthRequestToken(
        scopes=INIT['SCOPES'], oauth_callback=uri)
    secret = request_token.secret
    logging.info('Request Token fetched: %s' % request_token)
    logging.info('STEP 3: Set the fetched OAuth token.')
    gd_client.SetOAuthToken(request_token)
    logging.info('OAuth request token set.')
    logging.info('STEP 4: Generate OAuth authorization URL.')
    auth_url = gd_client.GenerateOAuthAuthorizationURL()
    
    logging.info('Authorization URL: %s' % auth_url)

    HttpResponseRedirect(auth_url)

    oauth_token = gdata.auth.OAuthTokenFromUrl(self.request.uri)
    if oauth_token:
      oauth_token.secret = secret
      oauth_token.oauth_input_params = service.GetOAuthInputParameters()
      service.SetOAuthToken(oauth_token)
      # Exchange the request token for an access token
      oauth_verifier = self.request.get('oauth_verifier', default_value='')
      access_token = service.UpgradeToOAuthAccessToken(
          oauth_verifier=oauth_verifier)
      # Store access_token to the service token_store for later access
      if access_token:
        service.current_token = access_token
        service.SetOAuthToken(access_token)

    self.redirect('/')

    logging.info('STEP 5: Upgrade to an OAuth access token.')
    gd_client.UpgradeToOAuthAccessToken()
    logging.info('Access Token: %s' % (
        gd_client.token_store.find_token(request_token.scopes[0])))
    return gd_client


def revoke_oauth_client(gd_client):
    print 'STEP 6: Revoke the OAuth access token after use.'
    gd_client.RevokeOAuthToken()
    print 'OAuth access token revoked.'

def get_some_users(client, usernames_only=False, limit=None, next_link=None):
    """Kinda like gdata.apps.service.AppsService.GetGeneratorForAllUsers() but
    we can step through list of users over multiple task-queue chunks.
    See also gdata.GDataService.GetGeneratorFromLinkFinder()

    Return (users_list, limit_remaning, next_link)
    limit_remaning can be passed in to next iteration as limit.
    next_link is None if done iterating.
    """
    # support debug mode where a limited list of usernames is provided
    if settings.DEBUG_WITH_ALL_USERS and usernames_only:
        if limit is not None:
            limit = limit - len(settings.DEBUG_WITH_ALL_USERS)
        return (settings.DEBUG_WITH_ALL_USERS, limit, None)

    users = []

    try:
        if next_link:
            userbunch = gdata.apps.UserFeedFromString(
                str(client.GetWithRetries(next_link)))
        else:
            userbunch = client.RetrievePageOfUsers()
        next = userbunch.GetNextLink()
        #logging.error("next link: %s" % next)
        if next is not None:
            next_link = next.href
        else:
            next_link = None
        for userentry in userbunch.entry:
            next_start_username = userentry.login.user_name
            if usernames_only:
                users.append(userentry.login.user_name)
            else:
                users.append(userentry)
            if (limit is not None) and (len(users) >= limit):
                next_link = None
                break
    except AppsForYourDomainException, e:
        error_code = getattr(e, 'error_code', '')
        reason = getattr(e, 'reason', '')
        invalidInput = getattr(e, 'invalidInput', '')
        logging.exception("AppsForYourDomainException trying to get user list for %s error_code=%r reason=%r invalidInput=%r e.args=%r",
            client.domain, error_code, reason, invalidInput, e.args)
        raise
        #return None

    if limit is not None:
        limit = max(limit - len(users), 0)
    return (users, limit, next_link)


def get_some_users_with_timeout(client, timeout=None, usernames_only=False, limit=None, next_link=None):
    """Repeatedly calls get_some_users() until timeout expires or limit is hit or all users fetched."""
    if timeout is None:
        return get_some_users(client, usernames_only, limit, next_link)
    start_time = time.time()
    allusers = []
    count_limit_remaining = limit
    while (time.time() - start_time) < timeout:
        someusers, count_limit_remaining, next_link = get_some_users(
            client, usernames_only=True, limit=count_limit_remaining, next_link=next_link)
        allusers.extend(someusers)
        if next_link is None:
            break
    return allusers, count_limit_remaining, next_link
