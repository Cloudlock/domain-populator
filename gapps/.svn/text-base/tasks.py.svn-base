from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import simplejson
import datetime
import hashlib
import itertools
import pickle
from copy import deepcopy

from google.appengine.ext import db
from google.appengine.api import taskqueue
from google.appengine.api import datastore_errors
from google.appengine.api import channel

from google.appengine.ext.db import TransactionFailedError
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api.datastore_errors import BadRequestError

try:
  # When deployed
  from google.appengine.runtime import RequestTooLargeError
except ImportError:
  # In the development server
  from google.appengine.runtime.apiproxy_errors import RequestTooLargeError

from gdata.apps.service import AppsForYourDomainException

#import history
#from models import DomainSetup, DomainUser, DomainUserCrawlChunk, BatchOperation
import models

from gdocsaudit import tools

import enqueue
from enqueue import *

def chunk_key_name(batch_id, prev_url):
    assert batch_id is not None
    if prev_url is None:
        prev_url_digest = ''
    elif prev_url == models.SCAN_START_MARKER:
        prev_url_digest = ''
    else:
        digest = hashlib.md5()
        digest.update(prev_url)
        prev_url_digest = digest.hexdigest()
    return 'ducc:' + batch_id + ':' + prev_url_digest

#def get_chunk_already_started(batch_id, prev_url):
#    return DomainUserCrawlChunk.get_by_key_name(chunk_key_name(batch_id, prev_url))

# run_in_transaction
#def _commit_new_chunk(domain, batch_id, usernamelist, requester_email, prev_url, next_url, user_crawl_started, task_queue_suffix):
#    chunk_name = chunk_key_name(batch_id, prev_url)
#    alreadyThere = DomainUserCrawlChunk.get_by_key_name(chunk_name)
#    if alreadyThere:
#        return alreadyThere
#    chunk = DomainUserCrawlChunk(key_name=chunk_name, domain=domain, batch_id=batch_id,
#        #user_crawl_started=user_crawl_started,
#        usernames_pending=usernamelist, requester_email=requester_email,
#        url=prev_url, next_url=next_url, task_queue_suffix=task_queue_suffix)
#    chunk.put()
#    enqueue_chunk_process(str(chunk.key()), queue_name=chunk.get_apicall_task_queue_name(), transactional=True)
#    return chunk

# run_in_transaction
#def _task_domain_user_scan_commit(dskey, mod, domain, usernamelist, newadmins, requester_email, batch_id):
#    ds = db.get(dskey)
#    for attr_name, value in mod.iteritems():
#        setattr(ds, attr_name, value)
#
#    if ds.user_crawl_count is None:
#        crawl_count = 0
#    else:
#        crawl_count = ds.user_crawl_count
#    # TODO: check that ds.next_user_url is still the old value we were operating on.
#    if mod['next_user_url']:
#        # still crawling
#        if usernamelist:
#            ds.user_crawl_count = crawl_count + len(usernamelist)
#        if newadmins:
#            ds.administrators_b.extend(newadmins)
#        enqueue_domain_user_crawl(domain, requester_email, batch_id=batch_id, transactional=True)
#    else:
#        # done!
#        if usernamelist:
#            ds.num_users = crawl_count + len(usernamelist)
#        else:
#            ds.num_users = crawl_count
#        ds.user_crawl_count = None
#        if newadmins:
#            ds.administrators = ds.administrators_b + newadmins
#        else:
#            ds.administrators = ds.administrators_b
#        ds.administrators_b = []
#        ds.user_crawl_completed = datetime.datetime.now()
#        ds.last_batch_id = batch_id
#    ds.put()
#    return ds

# called by domain_user_scan, name='gapps-domain-user-crawl', url=t/ucrawl/$domain
#def task_domain_user_scan(domain, requester_email, batch_id, current_retry_count):
#    """Task Queue handler for background scan of user list for domain."""
#    start_time = time.time()
#    ds = DomainSetup.get_for_domain(domain)
#    if current_retry_count >= settings.MAX_DOMAIN_CRAWL_FAILURES:
#        logging.error('too many failures (%d >= %d) scanning users for domain=%s',
#            current_retry_count, settings.MAX_DOMAIN_CRAWL_FAILURES, domain)
#        abort_domain_scan(ds)
#        return
#    crawl_count = ds.user_crawl_count
#    if crawl_count is None:
#        crawl_count = 0
#    next_link = ds.next_user_url
#    if next_link == models.SCAN_START_MARKER:
#        next_link = None
#    #if not next_link:
#        # Start it
#        crawl_count = 0
#        crawl_start = datetime.datetime.now()
#        mod = dict(
#            last_batch_id=None,
#            user_crawl_started=crawl_start,
#            user_crawl_completed=None,
#            #full_scan_completed=None,
#        )
#    else:
#        crawl_start = ds.user_crawl_started
#        mod = dict()
#    client = tools.get_gapps_client(requester_email, ds.domain, svc="prov")
#
#    prev_url = next_link
#    chunk = get_chunk_already_started(batch_id, next_link)
#
#    # Actually fetch some data.
#    # Even if chunk already started, refetch. Transaction on DomainSetup must have failed, and it needs its newadmins.
#    try:
#        (users_list, limit_remaning, next_link) = tools.get_some_users(
#            client, usernames_only=False, limit=None, next_link=next_link)
#    except AppsForYourDomainException, e:
#        if e.args and e.args[0] and e.args[0].get('body') and ('Unknown authorization header' in e.args[0]['body']):
#            logging.error('we are not authorized to run on domain %s', domain)
## TODO: count some number of consecutive failures and then disable the domain (by setting it expired)
##            if not ds.expiration_date:
##                ds.expiration_date = datetime.datetime.now()
##                logging.error('setting domain=%s expration to now', domain)
##                ds.put()
#            return
#        raise
#    logging.info('domain="%s" batch_id=%s found %d more users in %f seconds, next=%s',
#        domain, batch_id, len(users_list), time.time() - start_time, next_link)
#
#    newadmins = []
#    usernamelist = []
#    for u in users_list:
#        if u.login.admin == 'true':
#            newadmins.append(u.login.user_name)
#        usernamelist.append(u.login.user_name)
#        mod['next_user_url'] = next_link
#    if (not chunk) and usernamelist:
#        chunk = db.run_in_transaction(_commit_new_chunk, domain, batch_id, usernamelist, requester_email, prev_url, next_link, crawl_start, ds.task_queue_suffix)
#    elif chunk and usernamelist:
#        logging.warn('not re-committing chunk already found')
#    ds = db.run_in_transaction(_task_domain_user_scan_commit, ds.key(), mod, domain, usernamelist, newadmins, requester_email, batch_id)
#
#    logging.info("num_users and user_crawl_count: %s %s" % (ds.num_users, ds.user_crawl_count))
#
#    if not ds.next_user_url:
#        logging.info('finished user crawl of domain=%s batch_id=%s ds.last_batch_id=%s', domain, batch_id, ds.last_batch_id)
#
#        #TODO user crawl is finished here
#        enqueue_chunk_cleanup(domain=domain)
#
#        if ds.start_create_docs:
#            #progress_pct = int(100 * ds.user_crawl_count/ds.num_users)
#
#            progress = {
#                'progress_pct': "25"
#            }
#            message = simplejson.dumps(progress)
#            id = domain + "createdocs"
#            channel.send_message(id, message)
#
#            logging.info("Hit domain_create_docs")
#
#            #if request.method == "POST":
#            kwargs = {
#                #'owner': 'test',
#                #'domain': '',
#                'notify': '', #notify_new_owner and 'yes' or ''
#            }
#            op = BatchOperation(
#                domain = domain,
#                started_by = ds.installed_by,
#                op_name = 'listowners',
#                op_args = list(itertools.chain(*kwargs.items()))
#            )
#            op.put()
#
#            batch_id = op.key().id()
#            enqueue.enqueue_batch_start(batch_id)
#
#    else:
#        logging.info('domain=%s user_crawl_count=%d', domain, ds.user_crawl_count)
#        #TODO user crawl is still going need to update progress
#        if ds.start_create_docs:
#            progress_pct = int(25 * ds.user_crawl_count/ds.num_users)
#
#            progress = {
#                'progress_pct': str(progress_pct)
#            }
#            message = simplejson.dumps(progress)
#            id = domain + "createdocs"
#            channel.send_message(id, message)



# called by task_views.apicall, name='gapps-domain-task-apicall', url=t/apicall/(?P<domain>[^/]+)/r/(?P<rept_id>\d+)/u/(?P<username>[^/]+)/
#def task_apicall(accum, num_taskqueue_retries):
#    """APICALL task: get user data by making an API call, and add that data
#    to the provided UserAPIAccum accumulator."""
#
#    logging.info("Making apicall for user %s", accum.username)
#    start = time.time()
#    #accum.make_next_apicall(num_external_failures=num_taskqueue_retries)
#    apicall_time = time.time() - start
#
#    if apicall_time < 20:
#        logging.info('completed apicall for user %s of %d docs in %f seconds, going immediately to dbupdate', accum.username, accum.content_size(), apicall_time)
#        assert not accum.rept_id
#        try:
#            chunk_dbupdate(accum, 0)
#        except:
#            logging.exception('chunk_dbupdate failed for accum domain=%s user=%s, enqueue it', accum.domain, accum.username)
#            ds = DomainSetup.get_for_domain(accum.domain)
#            enqueue_dbupdate(accum, ds.get_dbupdate_task_queue_name(), transactional=False)
#        return
#
#    ds = DomainSetup.get_for_domain(accum.domain)
#    # no need to enqueue next task transactionally, because if that doesn't
#    # complete, then presumably the whole task_apicall request have blown
#    # up, resulting in a 500 response to the task queue manager, and causing
#    # the task to be re-queued using the previous accumulator data.
#    if accum.has_more_work():
#
#        if accum.content_size() >= settings.DRAIN_ACCUM_AFTER:
#            enqueue_dbupdate(accum, ds.get_dbupdate_task_queue_name(), transactional=False)
#        else:
#            enqueue_apicall(accum, ds.get_apicall_task_queue_name(), transactional=False)
#
#    else:
#        enqueue_dbupdate(accum, ds.get_dbupdate_task_queue_name(), transactional=False)


# transaction on DomainUser(ukey) object only
# See also accumulators.drain_onto_chunk_user_trans()
# run_in_transaction
def abort_user_scan(ukey, new_failures=None, too_many_failures=False):
    duser = db.get(ukey)
    if new_failures:
        duser.failures.extend(new_failures)
    duser.too_many_failures = too_many_failures
    duser.scan_tmp = None
    duser.needs_update = 0
    duser.next_uri = None
    duser.last_updated = datetime.datetime.now()
    duser.put()
    return duser


# transaction on DomainUserCrawlChunk(chunk_key) object only
#def _chunk_dbupdate_chunk_trans(chunk_key, duser):
#    """Part of chunk_dbupdate(). Mark one user as done."""
#    username = duser.username
#    chunk = db.get(db.Key(chunk_key))
#    if not chunk:
#        return None
#    if username in chunk.usernames_pending:
#        chunk.usernames_pending.remove(username)
#    if username in chunk.usernames_processing:
#        chunk.usernames_processing.remove(username)
#    if duser.too_many_failures:
#        if username not in chunk.usernames_failed:
#            chunk.usernames_failed.append(username)
#    elif duser.is_suspended:
#        if username not in chunk.usernames_suspended:
#            chunk.usernames_suspended.append(username)
#    else:
#        if username not in chunk.usernames_done:
#            chunk.usernames_done.append(username)
#    # The whole chunk is done
#    if (not chunk.usernames_pending) and (not chunk.usernames_processing):
#        chunk.finish_time = datetime.datetime.now()
#    chunk.put()
#    return chunk


CHUNK_BATCH_CHUNK_SIZE = 500


#def chunk_dbupdate(accum, num_taskqueue_retries):
#    # mostly non-transactional with idempotent one-row-transaction updates.
#    # Might:
#    #  transactionally update a DomainUser2 as suspended or api-failed
#    # or
#    #  update (many) DomainDocument2 records indpendently and then a DomainUser2 with document scan progress (and maybe start another apicall)
#    #
#    # and then, maybe:
#    #  update the DomainUserCrawlChunk the current user belongs to.
#    #  and then, maybe:
#    #   start_new_document_aggregation
#    assert accum.rept_id is None
#    #ds = DomainSetup.get_for_domain(accum.domain)
#    r = None
#    domain = accum.domain
#    du_key_name = DomainUser.make_key_name(domain, accum.username)
#    du_key = db.Key.from_path('DomainUser', du_key_name)
#    duser = None  # None just means not loaded yet
#    chunk = None  # None just means not loaded yet
#
#    logging.info("Draining data (size=%s) for %s..." % (accum.content_size(), du_key_name))
#
#    if num_taskqueue_retries > settings.MAX_DBUPDATE_FAILURES:
#        # ensure processing ceases for this user
#        accum.next_uri = None
#        accum.failed = True
#        msg = "Too many dbupdate attempts (%s). Giving up on this user." % num_taskqueue_retries
#        logging.error(msg)
#        accum.failures.append(msg)
#
#    # user modifications to commit later.
#    if accum.account_suspended:
#        nu = db.run_in_transaction_custom_retries(10, transactionallyUpdate, du_key, dict(is_suspended=True))
#        assert nu.is_suspended == True
#    elif accum.failed:
#        # the accumulator decided to give up on the user. Bye!
#        db.run_in_transaction_custom_retries(10, abort_user_scan, du_key, accum.failures, True)
#    else:
#        # the accumulator didn't fail, drain as normal if possible.
#        duser = db.get(du_key)
#        chunk = db.get(db.Key(accum.chunk_key))
#        if chunk is None:
#            # aborted
#            db.run_in_transaction(abort_user_scan, du_key)
#            return True
#        if not accum.can_drain_onto_chunk(chunk, duser):
#            logging.warn("accumulator cannot drain: cancelling this dbupdate and enqueing new apicall (next_uri=%s) instead." % duser.next_uri)
#            accum.decache()
#            newaccum = UserAPIAccum(rept_id=None, username=duser.username, domain=accum.domain,
#                                    duser=duser, chunk_key=accum.chunk_key)
#            enqueue_apicall(newaccum, queue_name=chunk.get_apicall_task_queue_name(), transactional=False)
#            return True
#        accum.apicall_queue = chunk.get_apicall_task_queue_name()
#        (duser, accum) = accum.drain_for_chunk(duser, domain, chunk)
#
#    if not accum.has_more_work():
#        logging.info("USER Done: %s@%s", accum.username, domain)
#        if duser is None:
#            duser = db.get(du_key)
#        assert duser is not None
#        chunk = db.run_in_transaction_custom_retries(20, _chunk_dbupdate_chunk_trans, accum.chunk_key, duser)
#
#        if chunk is None:
#            # was aborted
#            db.run_in_transaction(abort_user_scan, du_key)
#            return True
#        logging.info('chunk %s updated #pending=%d #processing=%d #done=%d #failed=%d #suspended=%d',
#            chunk.key().id_or_name(),
#            len(chunk.usernames_pending), len(chunk.usernames_processing),
#            len(chunk.usernames_done), len(chunk.usernames_failed),
#            len(chunk.usernames_suspended))
#        if chunk.usernames_pending:
#            # this chunk can't be done, it still has users to start.
#            chunk = maybe_enqueue_chunk_users_for_processing(chunk=chunk)
#        if chunk:
#            logging.info('chunk %s updated #pending=%d #processing=%d #done=%d #failed=%d #suspended=%d',
#                chunk.key().id_or_name(),
#                len(chunk.usernames_pending), len(chunk.usernames_processing),
#                len(chunk.usernames_done), len(chunk.usernames_failed),
#                len(chunk.usernames_suspended))
#            maybe_finish_chunk(chunk)
#
#        # TODO: Present usage-sorted users list.
#    return True

#def maybe_finish_chunk(chunk):
#    """If a chunk and all its batch-mates are done, start the final aggregation."""
#    if not chunk:
#        return
#    if chunk.finish_time is None:
#        return
#    # this chunk is done, check the rest of its batch.
#    logging.info('domain=%s chunk batch_id=%s ran %d users from %s to %s',
#        chunk.domain, chunk.batch_id, len(chunk.usernames_done), chunk.start_time, chunk.finish_time)
#
#    if not chunk.batch_id:
#        ### TODO: if chunk.post_completion_url... only for non-batch-id
#        ### chunks.
#
#        # We don't care about chunks not part of a whole-domain scan batch_id
#        return
#    # TODO: make the aggregation crawl pause N seconds if it gets to a chunk that isn't done!
#    # May need to .filter('finish_time >', 0) or so.
#    batchall = DomainUserCrawlChunk.all().filter('batch_id =', chunk.batch_id).fetch(CHUNK_BATCH_CHUNK_SIZE)
#    bcount = 0
#    bdone = 0
#    bactive = 0
#    for bent in batchall:
#        bcount += 1
#        if bent.finish_time is None:
#            bactive += 1
#        else:
#            bdone += 1
#    if bcount == CHUNK_BATCH_CHUNK_SIZE:
#        # Yes, until the code is smarter, this is an error.
#        logging.error('may have more than %d chunks for batch_id %s !', CHUNK_BATCH_CHUNK_SIZE, chunk.batch_id)
#    logging.info('batch %s count=%d done=%d active=%d', chunk.batch_id, bcount, bdone, bactive)
    #if bdone and (bactive == 0):
        # All chunks are done. Aggregate.
        # No need for this app
        #start_new_document_aggregation(chunk.domain, chunk.batch_id, chunk.user_crawl_started, queue_suffix=chunk.task_queue_suffix)


#def _task_domain_user_chunk_trans(dbk, new_users_and_accums, failed_users):
#    chunk = db.get(dbk)
#    if not chunk:
#        logging.error('chunk missing at transaction %s?', dbk)
#        return None
#    #accum_todo = []
#    needs_put = False
#    for username, accum in new_users_and_accums:
#        if username not in chunk.usernames_pending:
#            logging.warn('%s already moved out of pending, would have become processing', username)
#        else:
#            chunk.usernames_pending.remove(username)
#            chunk.usernames_processing.append(username)
#            #accum_todo.append(accum)
#            needs_put = True
#    for username in failed_users:
#        if username not in chunk.usernames_pending:
#            logging.warn('%s already moved out of pending, would have become failed', username)
#        else:
#            chunk.usernames_pending.remove(username)
#            chunk.usernames_failed.append(username)
#            needs_put = True
#    if not needs_put:
#        # this has already been entirely taken care of by other means.
#        return chunk
#
#    if (not chunk.usernames_pending) and (not chunk.usernames_processing):
#        chunk.finish_time = datetime.datetime.now()
#    chunk.put()
#   # for accum in accum_todo:
#   #     enqueue_apicall(accum, queue_name=chunk.get_apicall_task_queue_name(), transactional=True)
#
#    if ((len(chunk.usernames_pending) > 0) and
#        (len(chunk.usernames_processing) < settings.ACTIVE_USERS_PER_CHUNK_THROTTLE)):
#        # more users, need another nibble
#        enqueue_chunk_process(str(dbk), queue_name=chunk.get_apicall_task_queue_name(), transactional=True)
#    return chunk


# run_in_transaction
#def init_user_for_scanning(domain, username, accum, queue_name, force):
#    """Reterns created/updated DomainUser object, or None if we should skip it."""
#    key_name = DomainUser.make_key_name(domain, username)
#    duser = DomainUser.get_by_key_name(key_name)
#    if duser is None:
#        duser = DomainUser(key_name=key_name, username=username, domain=domain, next_uri=START_URI, needs_update=0)
#    else:
#        if duser.domain is None:
#            # fixup old model that lacked domain
#            duser.domain = domain
#        now = datetime.datetime.now()
#        if force or duser.needs_update:
#            # ignore any of the possible problems below
#            logging.info('init_user_for_scanning %s@%s needs_update', username, domain)
#        elif (now - duser.started) > settings.STUCK_USER_RESCAN_TIME:
#            # ignore other markers, rescan
#            logging.info('init_user_for_scanning %s@%s last scanned %s', username, domain, duser.started)
#        elif duser.next_uri == START_URI:
#            # is it okay to start another task, or should we really really not start another task?
#            logging.info('init_user_for_scanning skipping %s@%s has START_URI', username, domain)
#            return None
#        elif duser.next_uri is not None:
#            logging.warn('init_user_for_scanning skipping %s@%s has next_uri, skipping init. next_uri=%s', username, domain, duser.next_uri)
#            return None
#        elif duser.last_updated is None:
#            # assume user is newly created and being scanned
#            logging.warn('init_user_for_scanning skipping %s@%s has a scan started at %s, last_updated %s, skipping init.', username, domain, duser.started, duser.last_updated)
#            return None
#        elif duser.started > duser.last_updated:
#            # a scan was started after the last one finished.
#            logging.warn('init_user_for_scanning skipping %s@%s has a scan started at %s, last_updated %s, skipping init.', username, domain, duser.started, duser.last_updated)
#            return None
#        duser.needs_update = 0
#        duser.next_uri = START_URI
#        duser.scan_tmp = None
#        duser.too_many_failures = False
#        duser.failures = []
#        duser.debug_uri_log = []
#        duser.debug_num_docs_unique = 0
#        duser.started = now
#    duser.put()
#    #enqueue_apicall(accum, queue_name=queue_name, transactional=True)
#    return duser

#def maybe_enqueue_chunk_users_for_processing(chunk=None, chunk_key=None, chunk_key_str=None):
#    """Take any method of referring to a chunk. Return the updated chunk on progress, otherwise None."""
#    if chunk:
#        chunk_key = chunk.key()
#        chunk_key_str = str(chunk_key)
#    else:
#        if not chunk_key:
#            chunk_key = db.Key(chunk_key_str)
#        if not chunk_key_str:
#            chunk_key_str = str(chunk_key)
#        chunk = db.get(chunk_key)
#        if not chunk:
#            logging.error('no chunk for key %r (%s)?', chunk_key, chunk_key_str)
#            return None
#
#    # TODO: add a variable to DomainSetup (probably to be copied into chunk) to configure throttling per-domain as alternative to the global default in settings.py
#    next_batch_of_users = []
#    while (chunk.usernames_pending and
#        (len(next_batch_of_users) < settings.NUM_USERPROCS_TO_ENQUEUE_PER_NIBBLE) and
#        ((len(chunk.usernames_processing) + len(next_batch_of_users)) < settings.ACTIVE_USERS_PER_CHUNK_THROTTLE)):
#        next_batch_of_users.append(chunk.usernames_pending.pop())
#
#    if not next_batch_of_users:
#        return None
#
#    domain = chunk.domain
#    new_users_and_accums = []
#    failed_users = []
#
#    for username in next_batch_of_users:
#        logging.info('initting and starting accumulation for %s@%s', username, domain)
#        accum = UserAPIAccum(rept_id=None, username=username, domain=domain, chunk_key=chunk_key_str)
#        duser = db.run_in_transaction(init_user_for_scanning, domain, username, accum, chunk.get_apicall_task_queue_name(), False)
#        if duser is None:
#            failed_users.append(username)
#            continue
#        new_users_and_accums.append( (username, accum) )
#
#    # TODO: this transaction times-out more than I think it should. Where's the contention?
#    chunk = db.run_in_transaction_custom_retries(10, _task_domain_user_chunk_trans, chunk_key, new_users_and_accums, failed_users)

# domain_user_chunk 'gapps-domain-user-chunk' url=t/uchunk/
#def task_domain_user_chunk(chunk_key_str, current_retry_count):
#    """Do work on a DomainUserCrawlChunk."""
#    if current_retry_count >= settings.MAX_USER_CHUNK_FAILURES:
#        # mark whole chunk as failed
#        chunk_key = db.Key(chunk_key_str)
#        chunk = db.get(chunk_key)
#        if not chunk:
#            # was cancelled out from under us. okay.
#            return
#        logging.error('too many retries (%d >= %d) processing chunk domain=%s batch_id=%s',
#            current_retry_count, settings.MAX_USER_CHUNK_FAILURES,
#            chunk.domain, chunk.batch_id)
#        chunk = db.run_in_transaction_custom_retries(10, _task_domain_user_chunk_trans, chunk_key, [], list(chunk.usernames_pending))
#    else:
#        chunk = maybe_enqueue_chunk_users_for_processing(chunk_key_str=chunk_key_str)
#    if chunk:
#        maybe_finish_chunk(chunk)


DOMAIN_CLEANUP_CHUNK_FETCH_SIZE = 1000


# domain_user_chunk 'gapps-domain-chunk-cleanup' url=t/uchunk/
#def task_domain_chunk_cleanup(domain, current_retry_count):
#    """Return cursor if there is more work to do on this domain, or None."""
#    #start = time.time()
#    #batch_id = ds.last_batch_id
#    cursor = None
#    while True:
#        q = DomainUserCrawlChunk.all().filter('domain =', domain)
#        if cursor:
#            q.with_cursor(cursor)
#        to_del = []
#        count = 0
#        for chunk in q.fetch(DOMAIN_CLEANUP_CHUNK_FETCH_SIZE):
#            count += 1
#            #if chunk.batch_id != batch_id:
#            to_del.append(chunk)
#        db.delete(to_del)
#        logging.info('cleaned %d chunks from %s', count, domain)
#        if count < DOMAIN_CLEANUP_CHUNK_FETCH_SIZE:
#            # done
#            return None
#        # we hit the count limit, there may be more
#        cursor = q.cursor()
#        #if (stoptime is not None) and (time.time() > stoptime):
#        #   return cursor
#
#        # keep going, continue with loop, with cursor.

# run_in_transaction
#def _domain_stop_scan(ds_key):
#    ds = db.get(ds_key)
#    if not ds.next_user_url:
#        return ds
#    ds.next_user_url = None
#    ds.put()
#    return ds


#def abort_domain_scan(ds):
#    """Abort a scan for a DomainSetup object."""
#    logging.info('aborting scan for domain %s batch_id=%s', ds.domain, ds.last_batch_id)
#    ds = db.run_in_transaction(_domain_stop_scan, ds.key())
#    # TODO: make this work for more than 1000 chunks (1000*100 = 100,000 users)
#    db.delete(DomainUserCrawlChunk.all(keys_only=True).filter('batch_id =', ds.last_batch_id).fetch(1000))
#    # unlucky timing here could delete a completed aggregation. :-(
#    db.delete(DocumentAggregation.all(keys_only=True).filter('batch_id =', ds.last_batch_id).fetch(1000))
#    return ds