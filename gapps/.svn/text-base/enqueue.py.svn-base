from django.conf import settings
from django.core.urlresolvers import reverse
from google.appengine.ext import db
from google.appengine.api import taskqueue

import logging
import random
import time
from django.utils import simplejson


DEFAULT_QUEUE_SUFFIX = ''
#QUEUE_SUFFIXES = [''] + [ '-%03d' % x for x in range(1,4+1) ]
QUEUE_SUFFIXES = settings.QUEUE_SUFFIXES

APICALL_TASK_QUEUE_PREFIX = 'docreport-apicalls'
APICALL_TASK_QUEUE_NAME_DEFAULT = 'docreport-apicalls'

DBUPDATE_TASK_QUEUE_NAMES = [ 'docreport-dbupdates' ] + [ 'docreport-dbupdates-%03d' % x for x in range(1,4+1) ]
DBUPDATE_TASK_QUEUE_PREFIX = 'docreport-apicalls'
DBUPDATE_TASK_QUEUE_NAME_DEFAULT = 'docreport-dbupdates'

QUEUE_FOR_NIBBLES = 'docreport-nibbles'
QUEUE_FOR_DELETE = 'docreport-delete'
QUEUE_FOR_ACLMOD = 'docreport-aclmod'
QUEUE_FOR_AGGREGATE=APICALL_TASK_QUEUE_NAME_DEFAULT

#def enqueue_domain_user_crawl(domain, requester_email, batch_id=None, transactional=True):
#    """Enqueues a user crawl task for the given domain."""
#
#    logging.info("enqueue_domain_user_crawl for domain %s by %s, batch_id=%r", domain, requester_email, batch_id)
#
#    task_params = {'requester_email':requester_email}
#    if batch_id:
#        task_params['batch_id'] = batch_id
#    taskqueue.Task(
#        url=reverse("gapps-domain-user-crawl",
#                    # pass kwargs to make the logs more meaningful;
#                    # everything's actually read from the accum data
#                    kwargs=dict(domain=domain)),
#                    params=task_params,
#        ).add(queue_name=QUEUE_FOR_NIBBLES,
#              transactional=transactional)

#def enqueue_chunk_process(keystr, queue_name=None, transactional=True):
#    """Process a chunk of users from a crawl of a domain."""
#    if queue_name is None:
#        queue_name = APICALL_TASK_QUEUE_NAME_DEFAULT
#    t = taskqueue.Task(
#        url=reverse("gapps-domain-user-chunk"),
#        params=dict(id=keystr))
#    t.add(queue_name=queue_name,
#        transactional=transactional)
#    logging.info('enqueue_chunk_process name=%s keystr=%s', t.name, keystr)
#    return t

#def enqueue_apicall(accum, queue_name=None, transactional=True):
#    """Enqueues an APICALL task for the given accumulator."""
#    if queue_name is None:
#        queue_name = APICALL_TASK_QUEUE_NAME_DEFAULT
#    logging.debug("enqueue_apicall for user %s@%s on queue=%s" % (accum.username, accum.domain, queue_name))
#
#    taskqueue.Task(url=reverse("gapps-domain-task-apicall",
#                               kwargs=accum.get_url_params()),
#                   payload=accum.serialize(),
#                   ).add(queue_name=queue_name,
#                         transactional=transactional)

def enqueue_domain_document_create(domain, requester_email, transactional=False):#requester_email,
    logging.info("enqueue_domain_document_create for domain %s by %s", domain)#, requester_email)

    task_params = {'requester_email':requester_email}

    taskqueue.Task(
        url=reverse("gapps-domain-document-task",
                    kwargs=dict(domain=domain)),
                    params=task_params,

        ).add(queue_name=QUEUE_FOR_NIBBLES,
              transactional=transactional)

def enqueue_domain_userlist(domain, requester_email, units_pending, transactional=False):#requester_email,
    logging.info("enqueue_domain_userlist for domain %s by %s", domain)#, requester_email)

    queue_name = APICALL_TASK_QUEUE_PREFIX + random.choice(QUEUE_SUFFIXES)

    task_params = {'requester_email':requester_email,
                   'units_pending': simplejson.dumps(units_pending)}

    taskqueue.Task(
        url=reverse("gapps-domain-user-task",
                    kwargs=dict(domain=domain)),
                    params=task_params,

        ).add(queue_name=queue_name,
              transactional=transactional)

def enqueue_domain_maxusers(domain, requester_email, transactional=False):#requester_email,
    logging.info("enqueue_domain_maxusers for domain %s by %s", domain)#, requester_email)

    task_params = {'requester_email':requester_email}

    taskqueue.Task(
        url=reverse("gapps-domain-maxusers-task",
                    kwargs=dict(domain=domain)),
                    params=task_params,

        ).add(queue_name=QUEUE_FOR_NIBBLES,
              transactional=transactional)


def enqueue_batch_start(batch_id):
    queue_name = APICALL_TASK_QUEUE_PREFIX + random.choice(QUEUE_SUFFIXES)
    taskqueue.Task(url=reverse("gapps-domain-task-batch-start",
                               kwargs={ 'batch_id': batch_id }),
                   ).add(queue_name=queue_name)

def enqueue_batch_chunk(chunk_id, countdown=0):
    queue_name = APICALL_TASK_QUEUE_PREFIX + random.choice(QUEUE_SUFFIXES)
    taskqueue.Task(url=reverse("gapps-domain-task-batch-chunk",
                               kwargs={ 'chunk_id': chunk_id }),
                   countdown=countdown
                   ).add(queue_name=queue_name)


#def enqueue_chunk_cleanup(domain, current_domain=None, cursor=None, prev_domain=None, chunks_done=None, agg_cursor=None, transactional=False):
#    logging.info("enqueue_chunk_cleanup for current_domain=%s have cursor=%s prev_domain=%s", current_domain, bool(cursor), prev_domain)
#
#    task_params = dict(
#        current_domain=domain,
#        cursor=cursor,
#        prev_domain=domain,
#        chunks_done=chunks_done,
#        agg_cursor=agg_cursor,
#    )
#    taskqueue.Task(
#        url=reverse("gapps-domain-chunk-cleanup",
#                    kwargs=dict(domain=domain)),
#                    params=task_params,
#    ).add(queue_name=QUEUE_FOR_NIBBLES,
#          transactional=transactional
#    )
