#gapps.models

from appengine_django.models import BaseModel
from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils.safestring import mark_safe
from django.template import loader
from django.utils import simplejson
from google.appengine.ext import db


from gdocsaudit import tools
from gdata.apps.service import AppsForYourDomainException

import gdata
from gdata.acl.data import AclScope, AclRole
from gdata.docs.data import Acl

from google.appengine.api import datastore_errors
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from urllib import quote,unquote


import itertools
import logging
import datetime
#import json
import pickle
import random
import re
import time

import enqueue

from gapps.batch import get_handler

# Create your models here.

class DomainSetupAccessors(object):
    """Mixin for DomainSetupRenderWrapper and DomainSetup (model)."""
#    def get_user_count_limit(self):
#        """Return the user count limit applicable to this domain, based on
#        the domain's feature level."""
#        if self.feature_level != "paid":
#            return settings.FREE_TRIAL_USER_COUNT_LIMIT
#        else:
#            return None


#    def is_expired(self):
#        """Returns True iff I'm expired."""
#
#        if self.is_free_for_this_userbase():
#            return False
#
#        return self.expiration_date and self.expiration_date < datetime.datetime.now()

#    def is_free_for_this_userbase(self):
#        return self.num_users <= settings.FREE_FOR_UP_TO_N_USERS

#    def free_for_up_to_n_users(self):
#        return settings.FREE_FOR_UP_TO_N_USERS

    #def get_reports(self):
    #    if not hasattr(self, "_reports"):
    #        self._reports = list(DomainReport.all().ancestor(self.key()))

    #    return self._reports

    def get_pending_admin_actions(self):
        if not hasattr(self, "_pending_admin_actions"):
            self._pending_admin_actions = []
            #actions = AdminAction.all()\
            #        .ancestor(self.key())\
            #        .filter("status =", "pending")\
            #        .order("-when_issued")
            #for aa in actions:
            #    try:
            #        # related_obj may go away and cause ReferenceError
            #        assert aa.related_obj
            #        self._pending_admin_actions.append(aa)
            #    except:
            #        pass

        return self._pending_admin_actions


class DomainSetup(BaseModel, DomainSetupAccessors):
    #key: d:<DOMAIN|lowercase>

    domain = db.StringProperty(required=True)

    # List of admin usernames. These are GApps domain admins.
    administrators = db.StringListProperty()
    # administrators_b is being built by current crawl and will replace administrators when the user crawl completes.
    administrators_b = db.StringListProperty()
    # Persistent list of extra admins not in gdocs domain admins.
    custom_admins = db.StringListProperty()

    # username of installing user
    installed_by = db.StringProperty(required=True)

    installed_at = db.DateTimeProperty(auto_now_add=True,
                                       required=False,
                                       default=datetime.datetime(2010, 7, 14))

    # process state for deferred user list load
    #next_user_url = db.StringProperty()


    # DomainUserCrawlChunk.batch_id of the last completed user_crawl
    last_batch_id = db.StringProperty(indexed=False)
    # when this reaches limit we stop adding user data to the db, but keep scanning to find all admins.
    #user_crawl_count = db.IntegerProperty()
    #user_crawl_started = db.DateTimeProperty()
    #user_crawl_completed = db.DateTimeProperty()

    # A full scan runs from user_crawl_started to full_scan_completed.
    # After a scan completes, users and documents that haven't been updated
    # since before user_crawl_count may be deleted or inactive.
    #full_scan_completed = db.DateTimeProperty()

    # max(last current_crawl_user_count, self.get_user_count_limit())
    num_users = db.IntegerProperty(default=0)

    email_sent = db.BooleanProperty(default=False)

    users_to_create = db.IntegerProperty(default=0)

    service = db.BlobProperty(required=False)

    # the currently running report, if any
    # DEPRECATED - but I'm not sure what happens if you delete a property that exists in the datastore
    #active_report = db.ReferenceProperty(DomainReport, required=False,
    #                                     collection_name="domainsetup_active_set")
    # most recently completed report, if any
    # DEPRECATED - but I'm not sure what happens if you delete a property that exists in the datastore
    #latest_report = db.ReferenceProperty(DomainReport, required=False,
    #                                     collection_name="domainsetup_latest_set")

    # what is this account's feature level? free or paid?
#    feature_level = db.StringProperty(required=True,
#                                      choices=("free","paid"),
#                                      default="free")
    # if set, this domain account will expire and become unusable after the
    # given date.
    #expiration_date = db.DateTimeProperty(required=False, default=None)

    # email addresses to notify when report completes
    notify_on_report_completed = db.StringListProperty()

    # which task queue to use for this domain's dbupdates
    dbupdate_task_queue_name = db.StringProperty(required=False,
                                                 default=enqueue.DBUPDATE_TASK_QUEUE_NAME_DEFAULT)

    task_queue_suffix = db.StringProperty(required=False)

    # stores the time zone preference per user
    time_zone = db.StringProperty(default="UTC")

    #trigger for starting create docs scan
    #start_create_docs = db.StringProperty(required=False, default=None)

    #offset for creating users to make sure we don't always try creating the same users
    owner_offset = db.IntegerProperty(required=False, default=0)

    scan_status = db.StringProperty(required=False, default=None)

    user_limit = db.IntegerProperty(required=False, default=500)

    user_created_count = db.IntegerProperty(required=False, default=0)


    def get_dbupdate_task_queue_name(self):
        if self.task_queue_suffix and (self.task_queue_suffix in enqueue.QUEUE_SUFFIXES):
            return enqueue.DBUPDATE_TASK_QUEUE_PREFIX + self.task_queue_suffix
        if self.dbupdate_task_queue_name and (self.dbupdate_task_queue_name in enqueue.DBUPDATE_TASK_QUEUE_NAMES):
            return self.dbupdate_task_queue_name
        return enqueue.DBUPDATE_TASK_QUEUE_NAME_DEFAULT

    def get_apicall_task_queue_name(self):
        if self.task_queue_suffix and (self.task_queue_suffix in enqueue.QUEUE_SUFFIXES):
            return enqueue.APICALL_TASK_QUEUE_PREFIX + self.task_queue_suffix
        return enqueue.APICALL_TASK_QUEUE_NAME_DEFAULT

    @classmethod
    def get_for_domain(cls, domain, try_setup_as_user=None):
        """Returns a DomainSetup object for this domain, if it exists, or
        None if it hasn't been created yet. However, if a user object is
        provided in the try_setup_as_user parameter, and the DomainSetup
        hasn't been created yet, we will attempt to create it if the user is
        an administrator for the domain."""
        ds = cls.get_by_key_name("d:%s" % domain)
        if ds:
            return ds
        elif try_setup_as_user:
            return cls.get_for_domain_as_admin(domain, try_setup_as_user)

    @classmethod
    def get_for_domain_as_admin(cls, domain, current_user):
        """Returns a DomainSetup object for this domain, provided that the
        given user is an administrator in the domain.  If no DomainSetup
        entity for this domain exists yet, and current_user is an admin, it
        will be created and returned.  If current_user is not an admin,
        this function always returns None.
        """
        ds = cls.get_or_insert("d:%s" % domain,
                               domain= domain,
                               administrators= [],
                               installed_by= current_user.username,
                               #feature_level= settings.DEFAULT_FEATURE_LEVEL,
                               #expiration_date= datetime.datetime.now()+settings.DEFAULT_EXPIRATION_DELAY,
                               )

        #if len(ds.administrators) == 0 and ds.installed_by == current_user.username:

            # yes, we *did* just create this. Query for a list of admins.
            #logging.warn("DomainSetup: creating DomainSetup record for %s." % domain)
            #enqueue.enqueue_domain_user_crawl(domain, current_user.username, batch_id='1'+domain, transactional=False)

            # add the default schedule
            #ReportSchedule.set_default_schedule(DomainSetup=ds)

        if current_user.username.lower() not in map(lambda x: unicode(x).lower().strip(), ds.administrators):

            try:
                # last chance ... are you an admin?
                client = tools.get_gapps_client(current_user.email(), domain, svc="prov")
                user_record = client.RetrieveUser(current_user.username)

                if user_record.login.admin == 'true':
                    logging.warn("Admin found: %s" % current_user.username)
                    ds.administrators.append(current_user.username)
                    ds.put()
                    return ds
            except:
                logging.exception("Error looking for last-minute admin.")
                return None

            return None
        else:
            return ds

#    def send_completion_notifications(self, rept=None, dag=None):
#        """Send notification of DocumentAggergaton dag or DomainReport rept (deprecated)."""
#        from google.appengine.api import mail
#
#        rept_url = ""
#        if rept:
#            have_rept = True
#            rept_url = settings.DEPLOYED_URL + reverse(
#                "gapps-domain-admin-report-one",
#                kwargs=dict(domain=self.domain, rept_id=rept.key().id()),
#            )
#        else:
#            have_rept = False
#
#        if (not have_rept) and dag:
#            rept = dag
#            rept_url = settings.DEPLOYED_URL + reverse(
#                "gapps-domain-admin-report",
#                kwargs=dict(domain=self.domain),
#            )
#
#        dags = []
#        for dag in get_newest_domain_summaries(self.domain, 200):
#            # keep the 20 newest full aggregations
#            if dag.batch_id:
#                dags.append(dag)
#                if len(dags) >= 2:
#                    break
#
#        full_dags = get_exposure_list_changes(self.domain, dags)
#
#        date_format = "%m/%d/%Y"
#
#        if len(full_dags) > 1:
#            current_dag = full_dags[0]
#            prev_dag = full_dags[1]
#            cdag = current_dag['dag']
#            prev = prev_dag['dag']
#            start_time = prev.report_finish_time
#            end_time = cdag.report_finish_time
#            email_date_string = cdag.report_finish_time.strftime(date_format)
#        else:
#            current_dag = None
#            prev_dag = None
#            cdag = None
#            prev = None
#            if dag:
#                start_time = dag.report_start_time
#                end_time = dag.report_finish_time
#                email_date_string = dag.report_finish_time.strftime(date_format)
#            else:
#                start_time = None
#                end_time = None
#                email_date_string = None
#
#        if current_dag:
#            diff = current_dag['diff']
#            #Should be done with the template engine yet at this time we're still on django 1.1
#            #which doesn't support inequality comparisons.
#            has_more_public_adds = len(diff['public']['adds']) > settings.EMAIL_SECTION_LIMIT
#            has_more_public_dels = len(diff['public']['dels']) > settings.EMAIL_SECTION_LIMIT
#            has_more_outside_adds = len(diff['outside']['adds']) > settings.EMAIL_SECTION_LIMIT
#            has_more_outside_dels = len(diff['outside']['dels']) > settings.EMAIL_SECTION_LIMIT
#            has_more_everyone_adds = len(diff['everyone']['adds']) > settings.EMAIL_SECTION_LIMIT
#            has_more_everyone_dels = len(diff['everyone']['dels']) > settings.EMAIL_SECTION_LIMIT
#        else:
#            diff = None
#            has_more_public_adds = False
#            has_more_public_dels = False
#            has_more_outside_adds = False
#            has_more_outside_dels = False
#            has_more_everyone_adds = False
#            has_more_everyone_dels = False
#
#        ctx =  {"domain": self.domain,
#                "ds": self,
#                "rept": rept,
#                "dag": cdag,
#                "prev": prev,
#                "have_rept": have_rept,
#                "rept_url": rept_url,
#                "deployed_url": settings.DEPLOYED_URL,
#                "diff": diff,
#                "start_time": start_time,
#                "end_time": end_time,
#                "item_limit": ':' + str(settings.EMAIL_SECTION_LIMIT),
#                "email_date_string": email_date_string,
#                "has_more_public_adds": has_more_public_adds,
#                "has_more_public_dels": has_more_public_dels,
#                "has_more_outside_adds": has_more_outside_adds,
#                "has_more_outside_dels": has_more_outside_dels,
#                "has_more_everyone_adds": has_more_everyone_adds,
#                "has_more_everyone_dels": has_more_everyone_dels,
#                "to_email": None}
#
#        for to_email in self.notify_on_report_completed:
#            logging.info("Sending notification email to %s" % to_email)
#
#            ctx["to_email"] = to_email
#
#            subject = loader.render_to_string("gapps/_notify_email_subject.txt", ctx)
#            body = loader.render_to_string("gapps/_notify_email_body.txt", ctx)
#            html = loader.render_to_string("gapps/_notify_email_body.html", ctx)
#
#            message = mail.EmailMessage()
#            message.sender = settings.REPORT_COMPLETE_EMAIL_FROM
#            message.to = [to_email]
#            message.subject = subject
#            message.body = body
#            message.html = html
#
#            message.send()

#    def scan_in_progress(self):
#        """
#        Determine if a scan is in progress for this domain.
#        """
#        if self.next_user_url:
#            return True
#
#        ducs = DomainUserCrawlChunk.all().filter('batch_id', self.last_batch_id).fetch(1000)
#        for d in ducs:
#            if not d.finish_time:
#                return True
#
#        return False

class DomainSetupRenderWrapper(DomainSetupAccessors):
    """Copy elements from DomainSetup, with safe handling of ReferenceProperties."""
    def __init__(self, ds):
        self.ds = ds
        #self.domain = ds.domain
        #self.administrators = ds.administrators
        #self.installed_by = ds.installed_by
        #self.installed_at = ds.installed_at
        #self.num_users = ds.num_users
        self.active_report = None
        self.latest_report = None
        self._latest_aggr = None
        self._scan_progress = None
        #self.feature_level = ds.feature_level
        #self.expiration_date = ds.expiration_date
        #self.notify_on_report_completed = ds.notify_on_report_completed
        #self.dbupdate_task_queue_name = ds.dbupdate_task_queue_name
        try:
            self.active_report = ds.active_report
        except datastore_errors.Error, e:
            logging.warn('no active_report for domain=%s: %s', self.domain, e)
        try:
            self.latest_report = ds.latest_report
        except datastore_errors.Error, e:
            logging.warn('no latest_report for domain=%s: %s', self.domain, e)

    @property
    def latest_aggr(self):
        if self._latest_aggr is None:
            self.populate_latest_aggr_and_scan_props(self.ds)
        return self._latest_aggr

    @property
    def scan_progress(self):
        if self._scan_progress is None:
            self.populate_latest_aggr_and_scan_props(self.ds)
        return self._scan_progress

    def populate_latest_aggr_and_scan_props(self, ds):
        latest_aggr, scan_progress = get_latest_report_agg_scan_progress(self.domain, ds)
        self._latest_aggr = latest_aggr
        self._scan_progress = scan_progress

    def __getattr__(self, name):
        return getattr(self.ds, name)


# Dummy value to put in DomainSetup.next_user_url
# Lots of things check (ds.next_user_url is None) to see if a scan is on.
SCAN_START_MARKER = 'SCAN_START_MARKER'


def DSWrapperGenerator(dsetups):
    """For some iterable of DomainSetup objects, yield DomainSetupRenderWrapper objects."""
    for ds in dsetups:
        yield DomainSetupRenderWrapper(ds)


#class DomainUser(BaseModel):
#    username = db.StringProperty()
#    domain = db.StringProperty()
#    next_user = db.StringProperty(default = "START")

#    @classmethod
#    def get_for_user(cls, username, domain):
#        """Returns a DomainSetup object for this domain, provided that the
#        given user is an administrator in the domain.  If no DomainSetup
#        entity for this domain exists yet, and current_user is an admin, it
#        will be created and returned.  If current_user is not an admin,
#        this function always returns None.
#        """
#        du = cls.get_or_insert("du:%s:%s" % (domain, username),
#                               domain=domain,
#                               username=username,
#                               )

#        return du

#class DomainUserCrawlChunk(BaseModel):
#    # id: auto-assigned
#    # OR
#    # key_name = ducc:domain:batch_id:md5(url)
#    domain = db.StringProperty()
#    requester_email = db.StringProperty()
#    # when all chunks of a batch_id are done, the crawl is done. '%d%s' % (int(time.time()), domain)
#    batch_id = db.StringProperty()
#    # the gdocs API url that fetched these users
#    url = db.StringProperty()
#    # the gdocs API url that would fetch the next chunk of users
#    next_url = db.StringProperty()
#    # copied from DomainSetup.user_crawl_started for performance monitoring
#    #user_crawl_started = db.DateTimeProperty()
#    start_time = db.DateTimeProperty(auto_now_add=True)
#    finish_time = db.DateTimeProperty()
#    # pending: scanned user name.
#    usernames_pending = db.StringListProperty()
#    # processing: some documents from this user have been scanned.
#    usernames_processing = db.StringListProperty()
#    # done: all documents from this user's list have been scanned.
#    usernames_done = db.StringListProperty()
#    # failed: too mainy API failures.
#    usernames_failed = db.StringListProperty()
#    # suspended: user is inactive.
#    usernames_suspended = db.StringListProperty()
#    # copy in from DomainSetup so that deeply called enqueue_apicall can get it
#    task_queue_suffix = db.StringProperty(required=False, choices=enqueue.QUEUE_SUFFIXES)
#
#    # Like DomainSetup
#    def get_dbupdate_task_queue_name(self):
#        if self.task_queue_suffix:
#            return enqueue.DBUPDATE_TASK_QUEUE_PREFIX + self.task_queue_suffix
#        return enqueue.DBUPDATE_TASK_QUEUE_NAME_DEFAULT
#
#    # Like DomainSetup
#    def get_apicall_task_queue_name(self):
#        if self.task_queue_suffix:
#            return enqueue.APICALL_TASK_QUEUE_PREFIX + self.task_queue_suffix
#        return enqueue.APICALL_TASK_QUEUE_NAME_DEFAULT


class DomainUser(BaseModel):
    # NEW WAY:
    # key = du:$domain:$username


    # When creating DomainUser objects, set parent to a DomainSetup entity
    # just in case we need to do some transactions with that later.
    # (That also means we don't need to keep a ReferenceProperty to it.)

    username = db.StringProperty()
    #: Used for auto-complete as case sensitivity is required
    username_lower = db.StringProperty()
    domain = db.StringProperty()
    started = db.DateTimeProperty(auto_now_add=True)
    last_updated = db.DateTimeProperty()
    # Filter on this to find work to do. Higher number is higher priority.
    needs_update = db.IntegerProperty(default=1)

    #Flag for if a user is created by us
    created_by_us = db.BooleanProperty(default=False)



    # TODO: can this be handled more efficiently from the DomainDocument side scanning for presence of a user?
    # TODO: in the new world of updating users, how do documents get deleted from this list? what kind of history of that deletion could be stored?
    documents = db.ListProperty(db.Key)

    num_docs = db.IntegerProperty(default=0, verbose_name="Number of documents in this user's account (includes owned or collaborating).")
    num_docs_owned = db.IntegerProperty(verbose_name="Number of documents owned by this user.")
    num_docs_outside = db.IntegerProperty(default=0, verbose_name="Number of this user's documents shared outside the domain.")
    num_docs_everyone = db.IntegerProperty(default=0, verbose_name="Number of this user's documents shared with everyone in the domain.")
    num_docs_public = db.IntegerProperty(default=0, verbose_name="Number of this user's documents shared with the public internet.")

    # Category we fit into as per DocumentAggregation.histogram_splits
    usage_bucket = db.IntegerProperty()

    failures = db.StringListProperty(verbose_name="Failure messages during previous feed processing attempts, if any.")
    too_many_failures = db.BooleanProperty(default=False, verbose_name="True iff processing of this user was aborted due to too many failures.")

    is_suspended = db.BooleanProperty(default=False, verbose_name="True iff processing of this user is not possible because the account is suspended.")

    # temporaries while scanning things for this user
    debug_uri_log = db.StringListProperty(verbose_name="List of URIs queried for this user.")
    debug_num_docs_unique = db.IntegerProperty(default=0, verbose_name="Number of this user's documents shared outside the domain.")

    next_uri = db.StringProperty()
    # scan_tmp is a pickled dict
    scan_tmp = db.BlobProperty()


    def put(self, *args, **kwargs):
        if self.username:
            self.username_lower = self.username.lower()
        super(DomainUser, self).put(*args, **kwargs)

    # key = du:$domain:$username

    @staticmethod
    def make_key_name(domain, username):
        return 'du:%s:%s' % (domain, username)

    @staticmethod
    def make_key(domain, username):
        return db.Key.from_path('DomainUser', DomainUser.make_key_name(domain,username))

    @staticmethod
    def get_for_domain_user(domain, username):
        return db.get(DomainUser.make_key(domain, username))


class BatchMixin(object):
    """
    Methods that apply to both BatchOperation and BatchChunk, as they have
    duplicated fields.
    """

    @property
    def kwargs(self):
        """
        Supply the ``op_args`` field as a dictionary
        """
        from gapps import batch
        return dict(batch.utils.pair_up(self.op_args))

    def get_op_arg(self, key, decode=True):
        """
        Get an op arg via key.

        This interface mostly exists to interact with encoded values; for
        normal values, the :attr:`kwargs` property is preferred.
        """
        try:
            val = self.kwargs[key]
            if decode:
                return simplejson.loads(val)
            return val
        except KeyError:
            return None

    def set_op_arg(self, key, val, encode=False):
        """
        Set a `self.next_chunk_args` `key` to `val`.

        New keys are added as necessary. The instance is also saved.

        :param encode: JSON-encode the value?
        """
        kw = self.kwargs
        if encode:
            val = simplejson.dumps(val)
        else:
            val = str(val)
        kw.update({ key: val })
        self.op_args = list(itertools.chain(*kw.items()))
        self.put()

    def as_email(self, val):
        return '@'.join((val, self.domain))

    def reload(self):
        return db.get(self.key())

    def get_big_arg(self):
        """
        Get the ``big_arg`` value for this BatchOp/Chunk, as a python object.
        """
        if self.big_arg is None:
            return None

        return simplejson.loads(self.big_arg)

    def set_big_arg(self, value):
        """
        Set the ``big_arg`` value for this BatchOp/Chunk. Any
        JSON-serializable object can be set.
        """
        self.big_arg = simplejson.dumps(value)


class BatchOperation(BaseModel, BatchMixin):
    """
    Some batch-style operation taking place for a specific domain
    """
    #: The operation's "name" (more like a key), such as `xfer` for Transfer
    op_name = db.StringProperty(required=True)
    #: An operation/chunk's arguments in the form ``(key1, val1, key2, val2 ...)``
    op_args = db.StringListProperty()
    big_arg = db.TextProperty()
    domain = db.StringProperty()
    started_by = db.StringProperty()
    created_on = db.DateTimeProperty(auto_now_add=True)
    started_on = db.DateTimeProperty()
    finished_on = db.DateTimeProperty()
    #: How many times this operation has been delayed due to rate limit back-off
    delay_count = db.IntegerProperty(default=0)
    #: Operations may recursively build other operations; let them be associated
    parent_id = db.IntegerProperty(required=False)
    include_in_admin_action = db.BooleanProperty(default=True)
    #: Is Operation building chunks? False positives are possible for child ops.
    building = db.BooleanProperty(default=False)

    def get_admin_action(self):
        """
        Get or create an :class:`AdminAction` object for this operation.
        """
        existing = AdminAction.all().filter('related_obj', self).fetch(1)
        if existing:
            return existing[0]
        ds = DomainSetup.get_for_domain(self.domain)
        aa = AdminAction(parent = ds,
                         username = self.started_by or 'unknown',
                         action_type = 'batch_op',
                         related_obj = self)
        aa.put()
        return aa

    def start(self):
        """
        Start a BatchOperation.

        This is the only approved method for starting an operation. Logic here
        may migrate to new auto-called methods on handlers.
        """
        has_chunks = False

        if self.started_on:
            logging.error('BatchOperation %s already started.' % self.key().id())
            return
            #raise RuntimeError, 'BatchOperation %s already started.' % self.key().id()

        handler = get_handler(self)
        # TODO: enqueue should be transactional with put()
        handler.batch_starting()
        # Touch AdminAction to enable real-time status updates
        #self.get_admin_action()
        for chunk in handler._build_chunks():
            has_chunks = True
            enqueue.enqueue_batch_chunk(chunk.key().id())
        # Handle empty case and race w/ chunk completion
        handler.finish()

    @classmethod
    def unfinished_chunks_for(cls, batch_id):
        """
        Get a QuerySet of the unfinished chunks for a BatchOperation with id
        ``batch_id``
        """
        op = BatchOperation.get_by_id(batch_id)
        return op.get_unfinished_chunks()

    def get_unfinished_chunks(self):
        """
        Get a QuerySet of the unfinished chunks for this BatchOperation.
        """
        return BatchChunk.all().filter('batch_id',
            self.key().id()).filter('finished_on', None)

    def errors(self, include_children=True):
        """
        Get a list of errors for this batch.

        :param include_children: Include the progress of all children? If
            ``True``, force this call up the sibling hierarchy until we get to
            the parent.
        """
        if include_children and self.parent_id:
            return BatchOperation.get_by_id(self.parent_id).errors(True)

        errors = []
        children = list(BatchOperation.all()\
                                      .filter('parent_id', self.key().id())\
                                      .fetch(1000))
        for op in children + [self]:
            errors.extend(list(BatchUnitError.all().filter('batch_id', op.key().id())))

        return errors

    def progress(self, include_children=True):
        """
        Get the progress of this batch.

        :param include_children: Include the progress of all children? If
            ``True``, force this call up the sibling hierarchy until we get to
            the parent.

        :return: dict of the form:
            { pending: [...],
              done: [...],
              error: [...],
              skipped: [...] }

        """
        if include_children and self.parent_id:
            return BatchOperation.get_by_id(self.parent_id).progress(True)

        pending = []
        done = []
        err = []
        skipped = []
        children = []
        if include_children:
            children = list(BatchOperation.all()\
                                          .filter('parent_id', self.key().id())\
                                          .fetch(1000))
        for op in children + [self]:
            chunks = BatchChunk.all().filter('batch_id', op.key().id())
            for chunk in chunks:
                pending.extend(chunk.units_pending)
                done.extend(chunk.units_done)
                err.extend(chunk.units_error)
                skipped.extend(chunk.units_skipped)

        num_done = len(done)
        num_pending = len(pending)
        num_error = len(err)
        num_skipped = len(skipped)
        num_done_or_error = num_done + num_error + num_skipped
        num_total = num_done + num_pending + num_error

        if num_total:
            progress_pct = int(100 * num_done_or_error / num_total)
        else:
            progress_pct = 0

        return { 'pending': pending,
                 'done': done,
                 'error': err,
                 'skipped': err,
                 'num_done': num_done,
                 'num_pending': num_pending,
                 'num_error': num_error,
                 'num_skipped': num_skipped,
                 'num_done_or_error': num_done_or_error,
                 'num_total': num_total,
                 'progress_pct': progress_pct,
                 }
    
    def child_of(self, batch):
        """
        Sets this operation as the child of ``batch``.

        :type batch: :class:`BatchOperation`
        """
        self.parent_id = batch.key().id()
        # Here we take a liberty with reality to avoid some race conditions.
        # We mark the operation as "building" when it clearly isn't, but we
        # don't want the parent operation to complete before we even have a
        # chance to build (perhaps due to taskqueue lag) so we tell a little
        # while lie about our state.
        self.building = True
        return self
    
    def find_parent(self):
        """
        Find the parent of this operation, if any.
        """
        if not self.parent_id:
            return self
        return BatchOperation.get_by_id(self.parent_id).find_parent()

    def put(self):
        """
        Child operations don't get logged.
        """
        if self.parent_id:
            self.include_in_admin_action = False
        return super(BatchOperation, self).put()

class BatchChunk(BaseModel, BatchMixin):
    """
    A chunk of a BatchOperation, usually involving numerous pieces (`units`)
    """
    #: The operation's "name" (more like a key), such as `xfer` for Transfer
    op_name = db.StringProperty()
    #: An operation/chunk's arguments in the form ``(key1, val1, key2, val2 ...)``
    op_args = db.StringListProperty()
    big_arg = db.TextProperty()
    batch_id = db.IntegerProperty()
    domain = db.StringProperty()
    created_on = db.DateTimeProperty(auto_now_add=True)
    started_on = db.DateTimeProperty()
    finished_on = db.DateTimeProperty()
    units_pending = db.StringListProperty()
    units_done = db.StringListProperty()
    units_error = db.StringListProperty()
    #: Units that were skipped entirely due to a forced finish
    units_skipped = db.StringListProperty()
    latest_activity = db.DateTimeProperty()
    #: How many times this chunk has been delayed due to rate limit back-off
    delay_count = db.IntegerProperty(default=0)
    #: How many units we started with; handlers deal with it.
    unit_count = db.IntegerProperty(default=0)
    #: sequence number indicating when chunk was created
    seq_num = db.IntegerProperty(required=False)


class BatchUnitError(BaseModel):
    """
    Errors that occur as a result of processing a BatchChunk unit.
    """
    batch_id = db.IntegerProperty()
    chunk_id = db.IntegerProperty()
    #: An arbitrary value that handlers should know about
    code = db.IntegerProperty(default=0)
    #: A descriptive error message
    message = db.TextProperty(required=False)
    #: The unit in the error state
    unit = db.StringProperty()
    retries = db.IntegerProperty(default=0)
    last_error = db.DateTimeProperty(auto_now_add=True, auto_now=True)

    @classmethod
    def get_for(cls, unit, chunk, save=False):
        """
        Get the associated BatchError for a [unit, chunk] combo or create
        a new one.

        :param save: Save to the database before returning?
        """
        results = list(cls.all().filter('unit', unit)\
                                .filter('chunk_id', chunk.key().id())\
                                .filter('batch_id', chunk.batch_id))
        if len(results) == 1:
            return results[0]
        elif len(results) == 0:
            error = cls(unit = unit,
                        chunk_id = chunk.key().id(),
                        batch_id = chunk.batch_id)
            if save:
                error.put()
            return error

    def retry(self, queue=True, now=False):
        """
        Retry this error's unit by putting back on its chunk's units_pending
        stack. Either the entire chunk with be enqueued (`queue == True`) or
        the unit will appended to ``units_pending`` and saved.

        :param queue: re-queue the chunk?
        :param now: retry chunk now?
        """
        chunk = BatchChunk.get_by_id(self.chunk_id)
        handler = get_handler(chunk)
        units, chunk = handler.move_unit(chunk, 'error', 'pending', units=[self.unit])
        self.retries += 1
        self.save()
        if queue:
            enqueue.enqueue_batch_chunk(chunk.key().id())
        elif now:
            handler.process_chunk(chunk.reload())

    def __str__(self):
        return 'Unit %s failed: (%d) %s' % (self.unit, self.code, self.message)


class BatchCheckpoint(BaseModel):
    """
    A way to maintain consistency when building BatchChunks.

    See Batch documentation for proper usage.
    """
    batch_id = db.IntegerProperty()
    last_chunk_id = db.IntegerProperty()
    next_chunk_args = db.StringListProperty()
    updated_on = db.DateTimeProperty(auto_now_add=True, auto_now=True)

    @classmethod
    def set_checkpoint(cls, batch, *args):
        """
        Set a checkpoint for the given BatchOperation ``batch``.

        :param batch: The :class:`BatchOperation` object to create/update a
            checkpoint for.
        :param args: Arguments to save; used for the next time chunks are
            attempted to be built.
        """
        batch_id = batch.key().id()
        q = BatchChunk.all().filter('batch_id', batch_id).order('-created_on')
        try:
            last_chunk = q.fetch(1)[0]
        except IndexError:
            raise RuntimeError("Don't call set_checkpoint() on operations with "
                               "no chunks!")
        existing = cls.all().filter('batch_id', batch_id).fetch(1)
        if existing:
            bc = existing[0]
        else:
            bc = cls(batch_id=batch_id,
                     last_chunk_id=last_chunk.key().id())
        bc.next_chunk_args = [str(s) for s in args]
        bc.put()
        return bc

class DocTypeSetup(BaseModel):


    #Doc Type percentages
    #TODO might be better to have this in a list
    docratio = db.IntegerProperty(required=False, default=53)
    spreadratio = db.IntegerProperty(required=False, default=85)
    presratio = db.IntegerProperty(required=False, default=88)
    pdfratio = db.IntegerProperty(required=False, default=95)
    folderratio = db.IntegerProperty(required=False, default=100)
    #TODO add other doc types



class ShareSetup(BaseModel):

    #Outside users
    outsideuser1 = db.StringProperty(required=False, default="john.smith@externaluser1.com")
    outsideuser2 = db.StringProperty(required=False, default="externalcloudlockuser2@gmail.com")

    #Share percentages
    #TODO might be better to have this in a list

    shares20to22 = db.IntegerProperty(required=False, default=1)
    shares15to20 = db.IntegerProperty(required=False, default=2)
    shares10to15 = db.IntegerProperty(required=False, default=7)
    shares5to10 = db.IntegerProperty(required=False, default=22)
    shares3to5 = db.IntegerProperty(required=False, default=42)
    shares1to3 = db.IntegerProperty(required=False, default=62)
    shares0 = db.IntegerProperty(required=False, default=100)

    sharespublic = db.IntegerProperty(required=False, default=10)
    sharesdomain = db.IntegerProperty(required=False, default=10)
    sharesoutside1 = db.IntegerProperty(required=False, default=10)
    sharesoutside2 = db.IntegerProperty(required=False, default=10)

    shareexternal = db.BooleanProperty(required=False, default=True)

class NumDocSetup(BaseModel):

    #Num Docs percentages
    #TODO might be better to have this in a list
    numdocs300to125 = db.IntegerProperty(required=False, default=2)
    numdocs125to75 = db.IntegerProperty(required=False, default=3)
    numdocs75to25 = db.IntegerProperty(required=False, default=25)
    numdocs25to10 = db.IntegerProperty(required=False, default=55)
    numdocs10to5 = db.IntegerProperty(required=False, default=95)
    numdocs5to1 = db.IntegerProperty(required=False, default=100)
    limit = db.IntegerProperty(required=False, default=5000)
    userlimit = db.IntegerProperty(required=False, default=500)
    runtouserlimit = db.BooleanProperty(required=False, default=False)
    doccount = db.IntegerProperty(required=False, default=0)
    progress_doccount = db.IntegerProperty(required=False, default=0)
    progress_total = db.IntegerProperty(required=False, default=0)

class NumSiteSetup(BaseModel):

    #Num Sites percentages
    #TODO might be better to have this in a list
    numsites300to125 = db.IntegerProperty(required=False, default=2)
    numsites125to75 = db.IntegerProperty(required=False, default=3)
    numsites75to25 = db.IntegerProperty(required=False, default=25)
    numsites25to10 = db.IntegerProperty(required=False, default=55)
    numsites10to5 = db.IntegerProperty(required=False, default=95)
    numsites5to1 = db.IntegerProperty(required=False, default=100)
    limit = db.IntegerProperty(required=False, default=5000)
    userlimit = db.IntegerProperty(required=False, default=500)
    runtouserlimit = db.BooleanProperty(required=False, default=False)
    sitecount = db.IntegerProperty(required=False, default=0)
    progress_sitescount = db.IntegerProperty(required=False, default=0)
    progress_total = db.IntegerProperty(required=False, default=0)


class ServiceHelper(BaseModel):
    url = db.StringProperty(required=False)
    secret = db.StringProperty(required=False)
    oauth_verifier = db.StringProperty(required=False)
    access_token = db.BlobProperty()

