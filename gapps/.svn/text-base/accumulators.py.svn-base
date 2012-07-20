# Accumulators for GApps Docs Analysis

# system and google and other libraries
from copy import deepcopy
import datetime
import time

from collections import defaultdict
from itertools import chain
import logging, pickle, re
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db

from gdata.service import RequestError
from gdata.client import Unauthorized
import gdata.client

from gapps.models import DomainUser
import gapps.models as models
import gapps.enqueue as enqueue

from django.conf import settings
from django.utils.encoding import smart_unicode

# local imports
from gdocsaudit import tools
#from history import listDiff, entryDiff

START_URI = "//START//"

FOLDER_SCHEME_PREFIX = "http://schemas.google.com/docs/2007/folders/"

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S" # .%fZ"
DATETIME_STRING_SUFFIX_RE = re.compile(r'\.\d+Z')

MEMCACHE_TIME = 3600 # 1 hour


#class EmptyAccumulatorException(Exception):
#    """An accumulator was unexpectedly emptied!"""
#    pass
#
#class APICallRetryException(Exception):
#    """An apicall needs to be retried."""
#    pass

#class UserAPIAccum(object):
#
#    def __init__(self, rept_id, username, domain, next_uri=None, chunk_key=None, duser=None):
#        self.rept_id = rept_id
#        self.username = username
#        self.domain = domain
#        if next_uri:
#            self.next_uri = next_uri
#        else:
#            self.next_uri = START_URI
#        self.chunk_key = chunk_key
#        self.failures = []
#        self.uris_attempted = []
#        # a list in the form [(uri, [DocInfo, ...]), ...]
#        self.docs = []
#        self.last_drained_uri = None
#        self.failed = False
#        self.account_suspended = False
#        self.apicall_queue = None
#        assert (self.rept_id or self.chunk_key) and not (self.rept_id and self.chunk_key)
#        self.duser = None
#        if duser:
#            self.set_from_DomainUser(duser)
#
#    def get_url_params(self):
#        out = dict(rept_id=self.rept_id,
#                    domain=self.domain,
#                    username=self.username)
#        if out['rept_id'] is None:
#            out['rept_id'] = 0
#        return out
#
#    def log_failure(self, e):
#        logging.exception("Exception while processing user docslist.")
#
#        self.failures.append(repr(e))
#        logging.warn("** User %s now has %d failures." % (self.username,
#                                                          len(self.failures)))
##         # store debug info
##         du.debug_uri_log.append("%s -> %s" % (str(uri), "FAILED"))
##         du.debug_num_docs_unique += du.num_docs_unique
#
##         if len(self.failures) >= settings.MAX_API_FAILURES_PER_USER:
##             du.too_many_failures = True
#
##         # if there have been too many failures, just return my failed self!
##         if du.too_many_failures:
##             logging.warn("** User %s has too many failures. Giving up." % username)
##             return du
##         else:
##             # otherwise raise exception so that the request fails and
##             # queue will try again
##             raise
#
#    def process_docslist(self, docslist, uri):
#        """Go through the docslist and load its data into this accumulator."""
#
#        docdata = [ DocInfo.from_docEntry(d, self.domain) for d in docslist.entry ]
#
#        self.docs.append((uri, docdata))
#
#    def make_next_apicall(self, num_external_failures=0):
#        """Make an API call to the GDocs list data API at the next URL, as
#        stored in this accumulator, and add information from that API result
#        to this accumulator object.
#
#        If there's nothing more to do, returns immediately
#
#        May raise any exception encountered in fetching from that URL."""
#
#        if not self.has_more_work():
#            logging.info("called make_next_apicall but have no more work. returning.")
#            return
#
#
#        if (num_external_failures + len(self.failures)) > settings.MAX_API_FAILURES_PER_USER:
#            msg = "Failing user %s because of too many external (%d) and internal (%d) failures." % (
#                self.username,
#                num_external_failures,
#                len(self.failures))
#
#            logging.warn(msg)
#            self.failures.append(msg)
#
#            self.next_uri = None
#            self.failed = True
#            return # a dbupdate will be enqueued next.
#
#
#
#        client = tools.get_gapps_client("%s@%s" % (self.username, self.domain),
#                                        self.domain, "docsclient")
#        #  NOTE: to use v3 Docs List Data API instead of v2, add the
#        # "docsclient" parameter above. As of 2010-12-09, this is disabled
#        # because the v3 feed response doesn't include folder membership
#        # information; here's a question about that which I posted to Google:
#        # https://groups.google.com/group/google-documents-list-api/browse_thread/thread/ef36b98c1789213b
#
#        if self.next_uri == START_URI:
#            uri = None
#        else:
#            uri = self.next_uri
#
#        try:
#            uri_str = str(uri)
#            logging.info("GETTING DOCS LIST: uri=%s", uri_str)
#
#            self.uris_attempted.append(uri_str)
#
#            #docslist = tools.get_docs_with_acls(client, uri=uri)
#
#        except Unauthorized:
#            # v3 client - simple version
#            self.account_suspended = True
#            self.next_uri = None # signal no more work
#
#        except RequestError, e:
#            # v2 service - more complex
#            #import pdb, sys; pdb.Pdb(stdin=sys.__stdin__, stdout=sys.__stdout__).set_trace()
#            # TODO: find a more API-stable way of determining disabled account that checking for a string in the body?
#            if len(e.args) and e.args[0].get("status")==401 and "account has been disabled" in e.args[0].get("body"):
#                self.account_suspended = True
#                self.next_uri = None # signal no more work
#            else:
#                self.log_failure(e)
#                raise
#        except gdata.client.RequestError, e:
#            if e.status >= 500:
#                logging.error('gdata.client.RequestError status=%r reason=%r body=%r', e.status, e.reason, e.body)
#                raise APICallRetryException(e)
#            # otherwise fall through to not retry, just be done and call it failed.
#        except (urlfetch.DownloadError, Exception), e:
#            self.log_failure(e)
#            raise # must raise or else taskqueue will not re-run this job
#
#        else:
#            self.process_docslist(docslist, self.next_uri)
#
#            if docslist.GetNextLink():
#                self.next_uri = docslist.GetNextLink().href
#            else:
#                # no more API calls needed
#                self.next_uri = None
#            logging.debug('next_uri=%s', self.next_uri)
#
#    def has_more_work(self):
#        """Returns True iff additional API calls are needed to complete data
#        retrieval for this user."""
#        return not(self.next_uri is None) and not(self.account_suspended)
#
#    def memcache_key(self):
#        if self.rept_id is None:
#            assert self.chunk_key
#            return "UserAPIAccum_c:%s:%s:%s" % (self.username, self.domain, self.chunk_key)
#        else:
#            return "UserAPIAccum:%d:%s:%s" % (self.rept_id, self.username, self.domain)
#
#    def serialize(self):
#        """Get a binary string version of this object."""
#
#        k = self.memcache_key()
#
##        if (not self.docs) and (not self.uris_attempted) and (not self.failures):
##            # nothing gained by going to memcache
##            logging.debug('skipping memcache set for empty accumulator %s', k)
##            return k
#
#        logging.debug("Serializing %s. content_size=%d" % (k, self.content_size()))
#
#        memcache.set(k, self, time=MEMCACHE_TIME)
#
#        return k
#
#    def decache(self):
#        """Delete from memcache."""
#        return memcache.delete(self.memcache_key())
#
#    def pop_page(self):
#        """
#        Pop one page from the doc stack in an attempt to get around transaction
#        size restrictions
#        """
#        logging.warn("Popping a page from accumulator.")
#        try:
#            try:
#                page = self.docs.pop()
#            except IndexError: #empty
#                raise EmptyAccumulatorException
#            if len(self.docs) == 0:
#                raise EmptyAccumulatorException
#        except EmptyAccumulatorException:
#            logging.error("Got an empty accumulator as a result of popping a "
#                          "page off the document stack!")
#            raise
#        else:
#            self.next_uri = page[0]
#
#    def set_from_DomainUser(self, duser):
#        if len(duser.debug_uri_log):
#            self.last_drained_uri = duser.debug_uri_log[-1]
#        if duser.next_uri:
#            self.next_uri = duser.next_uri
#        self.duser = duser
#
#    @classmethod
#    def deserialize(cls, serial_form):
#        """Create an object from a previously serialized string."""
#        #return pickle.loads(serial_form)
#
#        logging.debug("deserializing %s", serial_form)
#
#        accum = memcache.get(serial_form)
#
#        if accum is not None:
#            return accum
#        if serial_form.startswith('UserAPIAccum_c'):
#            logging.info("%s not in memcache, reloading", serial_form)
#            # chunk mode
#            (classname, username, domain, chunk_key) = serial_form.split(":",3)
#            assert classname == 'UserAPIAccum_c'
#            accum = cls(rept_id=None, username=username, domain=domain, chunk_key=chunk_key)
#            # TODO: maybe there's a better flow for this so that the same duser fetch can be used at different levels of the apicall/dbupdate that this is in.
#            duser = DomainUser.get_for_domain_user(domain, username)
#            if not duser:
#                logging.error('no DomainUser to operate on domain=%s name=%s', domain, username)
#                return None
#            accum.set_from_DomainUser(duser)
#        else:
#            logging.warn("%s not in memcache, starting over", serial_form)
#            logging.error('rept_id based events should not be happening are DEPRECATED')
#            (classname, rept_id_str, username, domain) = serial_form.split(":",3)
#            assert classname == 'UserAPIAccum'
#            accum = cls(int(rept_id_str), username, domain)
#        return accum
#
#    def content_size(self):
#        """Returns the number of documents currently living inside this
#        accumulator. Intended for use in throttling updates, e.g. you only
#        update the DB if we're past a certain size."""
#        return sum([len(d[1]) for d in self.docs])
#
#    def can_drain_onto(self, drept, du):
#        """Return True iff this accumulator is OK to drain onto the given
#        report and username."""
#
#        logging.error('UserAPIAccum.can_drain_onto is DEPRECATED and should not be getting called.')
#
#        if drept.key().id() != self.rept_id:
#            logging.error("Cannot drain: my report id (%s) != %s" % (str(self.rept_id), str(drept.key().id())))
#            return False
#
#        if du.username != self.username:
#            logging.error("Cannot drain: my username (%s) != %s" % (self.username, du.username))
#            return False
#
#        if len(self.uris_attempted) == 0:
#            logging.error("Cannot drain: no URIs attempted!")
#            return False
#
#        if len(du.debug_uri_log) == 0:
#            if self.uris_attempted[0] is not None and self.uris_attempted[0] != "None":
#                logging.error("Cannot drain: URI mismatch: expected accum to start at None but starts at %s" % (self.uris_attempted[0]))
#                return False
#
#        else: # there are some URIs logged, we better match
#            if du.debug_uri_log[-1] != self.last_drained_uri:
#                logging.error("Cannot drain: URI mismatch: expected accum to have last drained at %s but actual self.last_drained_uri=%s" % (
#                        du.debug_uri_log[-1],
#                        self.last_drained_uri
#                        ))
#                return False
#
#
#        return True # rept, username, and URIs line up. OK to drain.
#
#    def drain(self, drept, du):
#        """Unload the contents of this accumulator upon the given
#        DomainReport and DomainUser objects. Assumed to be running inside a
#        transaction; objects are not saved."""
#
#        logging.error('UserAPIAccum.drain is DEPRECATED and should not be getting called.')
#        logging.info("DRAINING: rept %d, user %s: URIs %s --> %s. Last drained: %s" % (
#                drept.key().id(),
#                du.username,
#                self.uris_attempted[0],
#                self.uris_attempted[-1],
#                self.last_drained_uri,
#                ))
#
#        domain = drept.parent().domain
#
#        # always good to get the failures out of the way first.
#        du.failures.extend(self.failures)
#        self.failures = []
#        du.debug_uri_log.extend(self.uris_attempted)
#        self.uris_attempted = []
#
#        du.next_uri = self.next_uri
#
#        self.last_drained_uri = du.debug_uri_log[-1]

        #for d in chain(*[d[1] for d in self.docs]):
        #    dd = d.to_DomainDocument(drept, du.username)
#
#            du.num_docs += 1
#            du.documents.append(dd.key())
#
#            if d.is_exposed_outside:
#                du.num_docs_outside += 1
#            if d.is_exposed_everyone:
#                du.num_docs_everyone += 1
#            if d.is_exposed_public:
#                du.num_docs_public += 1


#            if (len(dd.writers)+len(dd.readers)) < (len(d.writers)+len(d.readers)):
#                logging.warn("************* %s ****************" % dd.doc_title)
#                logging.warn("Existing Document has LESS ACL info than d:")
#                logging.warn(" - dd writers: %r" % dd.writers)
#                logging.warn(" - dd reader: %r" % dd.readers)
#                logging.warn(" + d writers: %r" % d.writers)
#                logging.warn(" + d reader: %r" % d.readers)
#                logging.warn("*****************************")

#            if len(dd.folders) < len(d.folders):
#                logging.warn("************* %s ****************" % dd.doc_title)
#                logging.warn(" - dd folders: %r" % dd.folders)
#                logging.warn(" + d folders: %r" % d.folders)


#            if dd.first_found_as_user == du.username:
#                # time to count this toward domain totals.
#                du.debug_num_docs_unique += 1

#                drept.num_docs += 1
#                if dd.is_exposed_outside:
#                    drept.num_docs_outside += 1
#                if dd.is_exposed_everyone:
#                    drept.num_docs_everyone += 1
#                if dd.is_exposed_public:
#                    drept.num_docs_public += 1

#                # update drept.num_docs_t_<WHATEVER>
#                if dd.doc_type in KNOWN_DOC_TYPES:
#                    attrname = "num_docs_t_%s" % dd.doc_type
#                else:
#                    attrname = "num_docs_t_other"

#                prevct = getattr(drept, attrname)
#                setattr(drept, attrname, prevct + 1)

#                #du._num_docs_unique_by_type.setdefault(dd.doc_type,0)
#                #du._num_docs_unique_by_type[dd.doc_type] += 1

#            elif (len(dd.writers)+len(dd.readers)) < (len(d.writers)+len(d.readers)):
#                new_writers = set.difference(set(d.writers),
#                                             set(dd.writers))
#                new_readers = set.difference(set(d.readers),
#                                             set(dd.readers))

#                logging.warn("********* ADDING TO DOC ACL *********\nreaders += %s, writers += %s " % (new_readers,new_writers))

#                dd.writers += new_writers
#                dd.readers += new_readers

#                for collablist in (new_writers, new_readers):
#                    annotatedlist = DomainDocument.annotate_collab_list(domain, collablist)
#                    for collab in annotatedlist:
                        #logging.info(" ** reviewing collab %r" % collab)

#                        if collab.get("everyone"):
#                            if not dd.is_exposed_everyone:
#                                dd.is_exposed_everyone = True
#                                drept.num_docs_everyone += 1

#                        if collab.get("public"):
#                            if not dd.is_exposed_public:
#                                dd.is_exposed_public = True
#                                drept.num_docs_public += 1

#                        if collab.get("outside"):
#                            if not dd.is_exposed_outside:
#                                dd.is_exposed_outside = True
#                                drept.num_docs_outside += 1

                        # and update counts of insiders/outsiders
#                       if not(collab.get("everyone") or collab.get("public")):
#                            if collab.get("outside"):
#                                dd.count_outsiders += 1
#                            else:
#                                dd.count_insiders += 1

#                dd.put()

#        self.docs = [] # clear out the docs array!

#    def can_drain_onto_chunk(self, chunk, du):
#        """Return True iff this accumulator is OK to drain onto the given
#        report and username. (DomainUserCrawlChunk chunk, DomainUser du)"""
#
#        if str(chunk.key()) != self.chunk_key:
#            logging.error("Cannot drain: my chunk_key (%s) != %s", self.chunk_key, str(chunk.key()))
#            return False
#
#        if du.username != self.username:
#            logging.error("Cannot drain: my username (%s) != %s", self.username, du.username)
#            return False
#
#        if len(self.uris_attempted) == 0:
#            logging.error("Cannot drain: no URIs attempted!")
#            return False
#
#        if len(du.debug_uri_log) == 0:
#            if self.uris_attempted[0] is not None and self.uris_attempted[0] != "None":
#                logging.error("Cannot drain: URI mismatch: expected accum to start at None but starts at %s", self.uris_attempted[0])
#                return False
#
#        else: # there are some URIs logged, we better match
#            if not noneStrEq(du.debug_uri_log[-1], self.last_drained_uri):
#                logging.error(
#                    "Cannot drain: URI mismatch: du.debug_uri_log=%r self.last_drained_uri=%s",
#                    du.debug_uri_log,
#                    self.last_drained_uri)
#                return False
#
#
#        return True # rept, username, and URIs line up. OK to drain.

#    def drain_for_chunk(self, duser, domain, chunk):
#        """For DomainUserCrawlChunk chunk, DomainUser duser, do stuff."""
#        new_user_documents = []
#        num_docs_outside = 0
#        num_docs_everyone = 0
#        num_docs_public = 0
#        num_docs_owned = 0
#
#        # full user name
#        fullusername = duser.username + '@' + duser.domain
#        fullusername_lower = fullusername.lower()
#
#        # iterate through [(url, [docs]),...]
##        for dinfo in chain(*[d[1] for d in self.docs]):
##            dd = db.run_in_transaction_custom_retries(10, chunk_document_update, domain, duser, dinfo, chunk)
##            dd_key = dd.key()
##            if (dd.is_deleted != 0) and dd.scan_tmp is None:
##                logging.info('doc is_deleted %s %s', dd.doc_id, dd.is_deleted)
##                # TODO: this shouldn't be necessary. deleted documents don't show up in scan!
##                continue
##            new_user_documents.append(dd_key)
##            if dinfo.is_exposed_outside:
##                num_docs_outside += 1
##            if dinfo.is_exposed_everyone:
##                num_docs_everyone += 1
##            if dinfo.is_exposed_public:
##                num_docs_public += 1
##            if (dinfo.owner == fullusername) or (dinfo.owner == fullusername_lower):
##                num_docs_owned += 1
##        self.docs = [] # clear out the docs array!
#
#        logging.info('chunk-draining %s@%s last_drained_uri=%s, %s more docs', duser.username, domain, self.last_drained_uri, len(new_user_documents))
#        (duser, accum) = db.run_in_transaction_custom_retries(10,
#            drain_onto_chunk_user_trans,
#            duser.key(),
#            new_user_documents, num_docs_outside,
#            num_docs_everyone, num_docs_public,
#            num_docs_owned, self)
#        return (duser, accum)

# See also tasks.abort_user_scan
# run_in_transaction
#def drain_onto_chunk_user_trans(
#        user_key,
#        new_user_documents, num_docs_outside, num_docs_everyone, num_docs_public, num_docs_owned,
#        original_accum):
#    accum = deepcopy(original_accum) # in case this transaction is retried
#    duser = db.get(user_key)
#    if accum.failures:
#        duser.failures.extend(acum.failures)
#    accum.failures = []
#    if accum.uris_attempted:
#        logging.debug('attempted uri log %r', accum.uris_attempted)
#        duser.debug_uri_log.extend(accum.uris_attempted)
#    if duser.is_suspended and (not accum.account_suspended):
#        duser.is_suspended = False
#    accum.uris_attempted = []
#    accum.last_drained_uri = duser.debug_uri_log[-1]
#    duser.next_uri = accum.next_uri
#    if duser.scan_tmp:
#        counts = pickle.loads(duser.scan_tmp)
#    else:
#        counts = {'docs':[], 'num_docs_outside':0, 'num_docs_everyone':0, 'num_docs_public':0, 'num_docs_owned':0}
#    for dd_key in new_user_documents:
#        if dd_key not in counts['docs']:
#            counts['docs'].append(dd_key)
#    if num_docs_outside:
#        dictAdd(counts, 'num_docs_outside', num_docs_outside)
#    if num_docs_everyone:
#        dictAdd(counts, 'num_docs_everyone', num_docs_everyone)
#    if num_docs_public:
#        dictAdd(counts, 'num_docs_public', num_docs_public)
#    if num_docs_owned:
#        dictAdd(counts, 'num_docs_owned', num_docs_owned)
#    if accum.has_more_work():
#        duser.scan_tmp = pickle.dumps(counts)
#        enqueue.enqueue_apicall(accum, queue_name=accum.apicall_queue, transactional=True)
#    else:
#        duser.scan_tmp = None
#        duser.last_updated = datetime.datetime.now()
#        duser.documents = counts['docs']
#        duser.num_docs = len(duser.documents)
#        duser.num_docs_outside = counts['num_docs_outside']
#        duser.num_docs_everyone = counts['num_docs_everyone']
#        duser.num_docs_public = counts['num_docs_public']
#        duser.num_docs_owned = counts['num_docs_owned']
#        duser.needs_update = 0
#    duser.put()
#    return (duser, accum)