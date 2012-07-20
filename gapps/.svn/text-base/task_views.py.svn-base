# gapps.task_views - views for executing taskqueue operations

from decorators import taskqueue_only

#from gapps import batch, enqueue, models
#from gapps.batch.handlers import ChunkDelayed, ChunkUpdateError

from google.appengine.ext import db
from google.appengine.api import memcache

import gdata.acl.data
import gdata.docs.data
import gdata.docs.client
import gdata.apps.service
import gdata.apps.adminsettings.service

import os
import logging
import urllib
import traceback
import random
from docnames import doclist
from gapps.batch.handlers import ChunkDelayed, ChunkUpdateError

from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.conf import settings

import tasks
from models import DomainSetup, DomainUser, BatchOperation
import  models

from gdocsaudit.tools import get_gapps_client
import gdocsaudit.tools
import batch, enqueue

#import enqueue

#@taskqueue_only
#def domain_user_scan(request, taskinfo, domain):
#    tasks.task_domain_user_scan(domain, request.REQUEST['requester_email'], request.REQUEST.get('batch_id'), getRetryCount(taskinfo))
#    return HttpResponse("OK")

#@taskqueue_only
#def domain_user_chunk(request, taskinfo):
#    tasks.task_domain_user_chunk(request.REQUEST['id'], getRetryCount(taskinfo))
#    return HttpResponse("OK")

#@taskqueue_only
#def domain_chunk_cleanup(request, taskinfo, domain):
#    tasks.task_domain_chunk_cleanup(domain, getRetryCount(taskinfo))
#    return HttpResponse("OK")

def getRetryCount(taskinfo):
    v = taskinfo.get('TaskRetryCount')
    if not v:
        return 0
    try:
        return int(v)
    except ValueError:
        return 0
    return 0

#@taskqueue_only
#def apicall(request, taskinfo, domain, rept_id, username):
#    accum = UserAPIAccum.deserialize(request.raw_post_data)
#    if not accum:
#        return HttpResponse('fail')
#
#    num_taskqueue_retries = getRetryCount(taskinfo)
#
#    try:
#        tasks.task_apicall(accum, num_taskqueue_retries)
#    except APICallRetryException, e:
#        return HttpResponse("retry", status=500)
#    return HttpResponse("OK")

@taskqueue_only
def domain_enqueue_task(request, taskinfo, domain):# taskinfo,
    #enqueue.enqueue_domain_document_create(domain, request.REQUEST['requester_email'])
    ds = DomainSetup.get_for_domain(domain)
    logging.info("DomainSetup retrieved: %s", ds.domain)
    client = gdocsaudit.tools.get_gapps_client(request.REQUEST['requester_email'], ds.domain, svc="docsclient")
    #TODO ***gets list of users based on value in memcache and resets memcache if none found
    #feed = client.GetDocList()#uri='/feeds/' + request.REQUEST['requester_email'] + '/private/full')
    username = memcache.get("username")
    if username is None:
        username = DomainUser.all().filter('domain =', domain).get().username

    domain_user_list = DomainUser.all().filter('domain =', domain).filter('username >', username)
    results = domain_user_list.fetch(10)
    if not results:
        logging.error("No entries in feed.")
    last_result = None
    for duser in results:
        last_result = duser
        logging.info("User: %s", last_result.username)


    logging.info(last_result.username)
    success = memcache.set("username", last_result.username)
    if not success:
        logging.info("Unsuccessful memcache set")
    return HttpResponse("OK")


@taskqueue_only
def domain_enqueue_task_userlist(request, taskinfo, domain):# taskinfo,


    #TODO Create user
    ds = DomainSetup.get_for_domain(domain)
    logging.info("Requester Email: %s", request.REQUEST['requester_email'])
    #client = gdocsaudit.tools.get_gapps_client(request.REQUEST['requester_email'], ds.domain, svc="apps")

    #client = gdata.apps.service.AppsService(email='admin@testninjagdocs.com', domain='testninjagdocs.com', password='Apr1g0Lab')
    #client.ProgrammaticLogin()
    
    #user_name = "JOHN.SMITH"
    #family_name = "SMITH"
    #given_name = "JOHN"
    #password = "Apr1g0Lab"

    #try:

    #    new_user = client.CreateUser(user_name, family_name, given_name, password, suspended='false', quota_limit=gdata.apps.service.DEFAULT_QUOTA_LIMIT,password_hash_function=None)

    #except gdata.apps.service.AppsForYourDomainException, e:
    #    logging.info("Exception: %s", e)
    #logging.info("New User is: %s", new_user.login.user_name)


    client = gdata.apps.adminsettings.service.AdminSettingsService(email='admin@testninjagdocs.com', domain='testninjagdocs.com', password='Apr1g0Lab')
    client.ProgrammaticLogin()

    max_users = client.GetMaximumNumberOfUsers()
    current_users = client.GetCurrentNumberOfUsers()

    logging.info("max users: %s" % max_users)
    logging.info("current users: %s" % current_users)
    
    #maxusers = client.GetMaximumNumberOfUsers()
    #logging.info("Max users: %s", maxusers)
    #if not feed.entry:
    #    logging.error("No entries in feed.")
    #for entry in feed.entry:
    #    logging.info("User: %s@%s", entry.login.user_name,ds.domain)

    return HttpResponse("OK")

#@taskqueue_only
def domain_enqueue_task_maxusers(request, domain):# taskinfo,

    #TODO ****Getting unauthorized error - not sure why ****
    #ds = DomainSetup.get_for_domain(domain)
    #logging.info("Requester Email: %s", request.REQUEST['requester_email'])
    #client = gdocsaudit.tools.get_gapps_client(request.REQUEST['requester_email'], ds.domain, svc="adminsettings")
    #maxusers = client.GetMaximumNumberOfUsers()
    #logging.info("Max users: %s", maxusers)
    #if not feed.entry:
    #    logging.error("No entries in feed.")
    #for entry in feed.entry:
    #    logging.info("User: %s@%s", entry.login.user_name,ds.domain)



    #TODO get random number
    #rand = random.randint(0,len(doclist)-1) #(a<=N<=b)
    #logging.info('Random Number: %s' % rand)


    #logging.info(len(range(0,10)))

    #TODO get list of possible doc names
    #logging.info('Random Word: %s' % doclist[rand])

    #username = DomainUser.all().filter('domain =', domain).get().username
    username = 'admin'
    #TODO sign in as different user to create doc
    client = gdocsaudit.tools.get_gapps_client('@'.join((username,domain)), domain, svc="docsclient")


    feed = client.GetDocList()
    if not feed.entry:
        print 'No entries in feed.\n'
    for entry in feed.entry:
    #feed = client.GetDocList(uri='/feeds/documents/private/full/-/mine?max-results=1')
        acl_feed = client.GetAclPermissions(entry.resource_id.text)
        for acl in acl_feed.entry:
            logging.error('%s (%s) is %s' % (acl.scope.value, acl.scope.type, acl.role.value))

    #acl_feed = client.GetAclPermissions(doc.resource_id.text)
    #new_entry = user_email not in [acl.scope.value
    #for acl in acl_feed.entry:
    #    logging.error("ACLFEED: %s", )




    #TODO create users
    #TODO what happens when limit is reached

    

    return HttpResponse("OK")

@taskqueue_only
def domain_batch_start(request, taskinfo, batch_id):
    batch_op = models.BatchOperation.get_by_id(int(batch_id))
    batch_op.start()
    return HttpResponse("OK")

@taskqueue_only
def domain_batch_chunk(request, taskinfo, chunk_id):
    chunk = models.BatchChunk.get_by_id(int(chunk_id))
    try:
        handler = batch.get_handler(chunk)
        handler.process_chunk(chunk, count=chunk.unit_count)
    except ChunkDelayed:
        return HttpResponse("DELAYED")
    except ChunkUpdateError, e:
        logging.error('Error when updating chunk queues:\n%s', e.msg)
    except Exception:
        logging.critical('Uncaught exception while processing chunk #%s of operation #%s:\n%s',
                         chunk_id, chunk.batch_id, traceback.format_exc())

    if not handler.finished(chunk.reload()):
        enqueue.enqueue_batch_chunk(chunk_id)
    return HttpResponse("OK")
