"""
WARNING: Do NOT put feature-specific handlers in this module! It is for GENERIC
handlers ONLY!
"""

from __future__ import with_statement

import sys
import logging

from google.appengine.api import memcache
from google.appengine.api.app_logging import AppLogsHandler
from google.appengine.ext import db
from gdocsaudit import tools


class OperationStreamFormatter(logging.Formatter):
    def __init__(self, op, fmt=None, datefmt=None):
        logging.Formatter.__init__(self, fmt, datefmt)
        self.op_id = op.key().id()
        self.domain = op.domain or '<nodomain>'

    def format(self, record):
        record.op_id = self.op_id
        record.domain = self.domain
        return logging.Formatter.format(self, record)


class UnitError(Exception):
    """
    To be raised during the processing of a unit.
    """
    #: Is this based on a RequestError?
    is_reqerr = False
    #: Possible formatted traceback
    tb = ''

    def __init__(self, unit, op, code=0, msg='', req=None, tb=''):
        self.unit = unit
        self.op = op
        self.is_reqerr = bool(req)
        if req:
            self.code = req.status
            self.msg = req.body
            self.tb = tb
        else:
            self.code = code
            self.msg = msg

    def should_retry(self):
        """
        Can this error be retried?
        """
        return (not self.code in self.noretry) and not "You can't yet" in self.msg

    def is_rate_limit(self):
        """
        Is this error considered a rate limit hit?
        """
        return (self.code in self.ratelimit
               and not "You can't yet" in self.msg
               and not 'permission' in self.msg)

    def __unicode__(self):
        full_msg = '\n'.join((self.msg, self.tb))
        return 'Unit %s of Operation #%s: %s' % (self.unit,
                                                  self.chunk.key().id(),
                                                  self.meta.key().id(),
                                                  full_msg)
    __str__ = __unicode__


class BaseHandler(object):
    """
    The base handler for all Operations.
    
    Any new handler should inherit from me, and implement the following methods:

    * :meth:`iterunits`
    * :meth:`do_unit`

    You may also wish to provide alternative methods for those labeled
    *Callback*.
    """
    #: Number of units to work in parallel
    concurrency = 5
    #: User-friendly name for this type of Operation
    op_label = 'Batch Operation v2.0'
    #: User-friendly unit label for this type
    unit_label = 'Unit'
    #: User-friendly verbose unit label for this type
    unit_label_verbose = 'Units'
    #: Metadata of the running Operation (:class:`OperationMeta` instance)
    meta = None
    #: Maximum number of times to retry a unit
    retry_max = 5
    #: Don't retry on these codes (default: 404)
    noretry_codes = None
    #: Delay on these codes (default: 403, 503, 400, 500)
    delay_codes = None
    #: How long to delay attempting to finish the operation. See documentation.
    finish_delay = 0
    #: Custom logger created at instantiation; use me instead of :mod:`logging`
    log = None

    def __init__(self, meta):
        self.meta = meta

        # Map over handler overrides
        data = self.meta.data
        if isinstance(data, dict):
            overrides = data.get('handler_attrs', {})
            for attr, value in overrides.items():
                setattr(self, attr, value)

        if self.noretry_codes is None:
            self.noretry_codes = [404]

        if self.delay_codes is None:
            self.delay_codes = [403, 503, 400, 500]

        self.log = self.get_logger()

    def get_logger(self, name='units', single_handler=True, cls=logging.Logger,
                   **kwargs):
        """
        Create an AppEngine-friendly logger.

        The logger will (a) not duplicate log messages in the root logger and
        (b) ensure entries are logged at their proper level. Access me as
        :attr:`log` and use me instead of the standard :mod:`logging`
        package--I automatically include vital Operation info in every message!

        :param cls: A custom logger class
        :param single_handler: Enforce that the logger only ever has one handler?
        :param kwargs: Any attributes to set on the instantiated ``cls``. This
            hack allows us to have "special" loggers that have access to more
            than a ``name`` attribute.
        """
        logging.setLoggerClass(cls)
        # Filter out messages not meant for the root logger
        root = logging.getLogger()
        if len([f for f in root.handlers[0].filters if f.name == 'root']) == 0:
            filtr = logging.Filter('root')
            root.handlers[0].addFilter(filtr)
        datefmt = 'OP#%(op_id)-6s %(domain)s: %(levelname)-7s %(message)s'
        formatter = OperationStreamFormatter(self.meta, datefmt)
        # GAE-specific stream handler
        handler = AppLogsHandler()
        handler.setFormatter(formatter)
        log = logging.getLogger(name)
        if single_handler and len(log.handlers) > 0:
            log.handlers[0] = handler
        else:
            log.addHandler(handler)
        for key, val in kwargs.items():
            setattr(log, key, val)
        # Reset logger class
        logging.setLoggerClass(logging.Logger)
        return log

    def prerun(self):
        """
        *Callback*

        Called immediately before an operation is run.

        If this handler is configured to allow multiple operation starts (e.g.
        in case of exception during unit iteration), this may be called
        multiple times.
        """
        raise NotImplementedError()

    def op_done(self):
        """
        *Callback*

        Called immediately after an Operation has completed.
        """
        raise NotImplementedError()

    def op_failed(self):
        """
        *Callback*

        Called after an Operation has failed to run too many times.
        """
        raise NotImplementedError()

    def group_done(self):
        """
        *Callback*

        Called immediately after a group of Operations has completed.
        
        If you define this callback it will be called even for single
        operations, but is guaranteed to only be called once per group.
        """
        raise NotImplementedError()

    def iterunits(self, *args, **kwargs):
        """
        *Callback*

        Yield units to be worked on.

        :returns: generator which yields units of work
        :rtype: string
        """
        raise NotImplementedError()

    def do_unit(self, unit): 
        """
        *Callback*

        Do the actual processing of a unit.

        Sub-classes must override.
        """
        raise NotImplementedError()

    def unit_done(self, unit, success, retrying):
        """
        *Callback*

        The unit is done. This is guaranteed to be called once per unit
        regardless of its final state.

        :param success: Whether or not the task succeeded. Rate limits are
            considered failures.
        :type success: bool
        :param retrying: Whether or not the unit is being retried (irrelevant
            when ``success==True``)
        :type retrying: bool
        """
        raise NotImplementedError()

    def unit_error(self, unit, err):
        """
        *Callback*

        A unit has raised an exception.

        After processing the error, be sure to re-raise an instance of
        :class:`UnitError` to continue error processing. Returning assumes
        you have resolved the issue and the unit will be marked as finished.

        :param err: The processed error raised
        :type err: ChunkUnitError
        :param unit: The unit attempted
        :raises: :class:`UnitError` to continue error processing; any other
            Exception becomes the new base exception
        """
        raise err

    def unit_delay(self, unit, op_delay=True):
        """
        *Callback*

        The unit was delayed. Raise :class:`units.exc.TooManyDelays` here to
        override any delay handling. Other exceptions will be logged and
        ignored.

        :param op_delay: Was it delayed based on an Operation-level delay?
        """
        raise NotImplementedError()


class Bootstrap(BaseHandler):
    """
    Handler capable of generating units via :func:`bootstrap`.
    """
    _finish_delay = 30
    max_runs = sys.maxint

    @property
    def finish_delay(self):
        # We could reload self.meta here to get a more up-to-date oparg value,
        # but since try_unit() re-inits them on each run, it really shouldn't
        # be a big deal.
        return int(self.meta.get_op_arg('finish_delay', self._finish_delay))

    def iterunits(self):
        """
        Yield units based on existing units found in bulk data field.
        """
        if isinstance(self.meta.data, dict):
            for unit in self.txn_empty_units():
                yield unit

    def txn_empty_units(self):
        units = []
        meta = self.meta.reload()
        existing = meta.data
        if isinstance(existing, dict):
            units = existing.get('bootstrap_units', [])
            existing['bootstrap_units'] = []
            meta.data = existing
            meta.put()
        return units


class StatStorage(BaseHandler):
    """
    Persist statistics for an Operation current in memcache.
    """
    def op_done(self):
        """
        Find stats in memcache and store them in the datastore.
        """
        from units.models import OperationStats

        to_delete = []
        oid = self.meta.key().id()
        pid = self.meta.parent_id or 0
        key_name = 'units:%d:%d:stats' % (pid, oid)
        stats = OperationStats.get_or_insert(key_name, op_id=oid, parent_id=pid)

        enq_key = self.meta.mk_cache_key('num_tasks_enqueued')
        enq = memcache.get(enq_key)
        count_key = self.meta.mk_cache_key('task_runtimes_counted')
        count = memcache.get(count_key)

        if enq is not None:
            stats.num_tasks_enqueued = int(enq)
            to_delete.append(enq_key)
        if count is not None:
            to_delete.append(count_key)
            for x in range(1, int(count) + 1):
                runtime_key = self.meta.mk_cache_key('task_runtime_%d' % x)
                val = memcache.get(runtime_key)
                if val is not None:
                    to_delete.append(runtime_key)
                    stats.task_runtimes.append(float(val))
                if len(to_delete) > 100:
                    memcache.delete_multi(to_delete)
                    to_delete = []
        stats.put()
        memcache.delete_multi(to_delete)


class FeedIterator(BaseHandler):
    """
    Iterate through a paged Google API feed, following next links.

    Built around :meth:`get_page` which, given a start url, returns a "page" of
    units and, possibly, a next url. :meth:`iterunits` will yield units one by
    one.

    This handler also takes care of error recovery by starting from the last
    "next_url" and skipped previously-yielded units.
    """
    max_runs = 5

    def __init__(self, *args, **kwargs):
        super(FeedIterator, self).__init__(*args, **kwargs)

        data = self.meta.data
        if data and not isinstance(data, dict):
            raise ValueError('FeedIterator handler requires operation data as '
                             'dictionary or empty!')
        elif not data:
            self.meta.data = {}
            self.meta.put()

    def update_progress(self, next_url, prev_units=None):
        """
        Transactional.
        """
        prev_units = prev_units or []

        meta = self.meta.reload()
        data = meta.data
        data['feed_iterator_progress'] = {
            'next_url': next_url,
            'prev_units': prev_units
        }
        meta.data = data
        meta.put()
        return meta

    def get_progress(self):
        """
        Transactional.
        """
        meta = self.meta.reload()
        progress = meta.data.get('feed_iterator_progress')
        if progress:
            return(progress.get('next_url'), set(progress['prev_units']))

        return (None, set())

    def get_page(self, start_url=None):
        """
        Produce one page of results, and possibly a next url.

        :returns: (next_url, page_units), where next_url is a string (or
            ``None`` if we're done) and page_units is a list of strings.

        OVERRIDE THIS.
        """
        next_url = None
        page_units = []
        return next_url, page_units

    def iterunits(self, start_url=None):
        """
        Do not override this.
        """
        prev_units = []
        curr_units = []

        if not start_url:
            start_url, prev_units = db.run_in_transaction(self.get_progress)

        # get some units
        next_url, page_units = self.get_page(start_url=start_url)

        try:
            for unit in page_units:
                if unit not in prev_units:
                    curr_units.append(unit)
                    yield unit
        except Exception:
            db.run_in_transaction(self.update_progress, next_url, curr_units)


        if next_url:
            db.run_in_transaction(self.update_progress, next_url)
            self.iterunits(next_url)


class UserGenerator(FeedIterator):
    """
    Generate users in a domain as units.
    """
    def get_page(self, start_url=None):
        """
        Get a page of user units, and possibly a next url.
        """
        auth = self.meta.kwargs.get('auth')

        assert auth, "SitesScan opargs must include 'auth' email/username"

        if '@' not in auth:
            auth = "@".join((auth, self.meta.domain))

        client = tools.get_gapps_client(svc="prov", *auth.split('@'))

        (users_list, _, new_next_url) = tools.get_some_users_with_timeout(
            client, timeout=60 * 5, usernames_only=True, limit=None,
            next_link=start_url
        )

        return new_next_url, users_list


class CompositeHandler(list):
    """
    Use numerous handlers as if they were one.

    A given callback will be called for each handler. Those raising
    :class:`NotImplementedError` will pass silently. Any other exception will
    break the callback chain. Callbacks are always called in order.
    """
    def __init__(self, init, op):
        instances = [i(op) for i in init]
        super(CompositeHandler, self).__init__(instances)

    def call(self, callback, *args, **kwargs):
        """
        Call ``callback`` with ``args`` and ``kwargs`` on each handler.
        """
        returns = []
        for handler in self:
            cb = getattr(handler, callback)
            try:
                returns.append(cb(*args, **kwargs))
            except NotImplementedError:
                pass
        return returns

    def attr(self, name, default=None, cast=None):
        """
        Get a list of attribute values.

        :attr default: Used in case of missing value
        :attr cast: Function used to coerce value
        """
        attrs = []
        if not callable(cast):
            cast = lambda x: x

        for handler in self:
            try:
                attr = getattr(handler, name)
            except AttributeError:
                pass
            else:
                if not isinstance(attr, (list, set, tuple)):
                    attr = [attr]
                attrs.extend([cast(a) for a in attr])

        if not attrs and default is not None:
            attrs = [default]

        return attrs

    def set(self, name, value):
        """
        Set an attribute on each handler.
        """
        for handler in self:
            setattr(handler, name, value)

    @property
    def multi(self):
        return len(self) > 1

