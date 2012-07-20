import pickle
import itertools
from datetime import datetime, timedelta
from collections import defaultdict

from appengine_django.models import BaseModel
import simplejson as json
from google.appengine.ext import db

from shard import ShardedQueue, ShardedCounter

import units
from units import loader, handlers


class OperationMeta(BaseModel):
    """
    Some batch-style operation taking place for a specific domain
    """
    #: Operation's handlers' dotpaths
    handlers = db.StringListProperty()
    #: Operation's backend dotpath
    backend = db.StringProperty(indexed=False,
                                default='units.backends.PushQueueBackend')
    #: An operation's arguments in the form ``(key1, val1, key2, val2 ...)``.
    #: Use ``kwargs`` to access.
    args = db.StringListProperty()
    #: Stores a JSON text blob. Use ``data`` to get/set the value using Python
    #: primitives.
    json = db.BlobProperty(indexed=False)
    #: Operation's domain, if relevant
    domain = db.StringProperty()
    #: Who started it
    started_by = db.StringProperty()
    created_on = db.DateTimeProperty(auto_now_add=True)
    started_on = db.DateTimeProperty(default=None)
    finished_on = db.DateTimeProperty(default=None)
    failed_on = db.DateTimeProperty(default=None)
    finish_attempts = db.IntegerProperty(default=0)
    group_finished_on = db.DateTimeProperty(default=None)
    #: Number of times we've tried running this Operation
    run_count = db.IntegerProperty(default=0)
    #: How many times this operation has been delayed
    delays = db.IntegerProperty(default=0)
    #: Current delay value in seconds
    current_delay = db.IntegerProperty(default=0)
    #: Operations may recursively build other operations; let them be associated
    parent_id = db.IntegerProperty(required=False)
    #: Number of shards per queue for this operation
    shard_count = db.IntegerProperty(default=20, indexed=False)

    def start(self):
        """
        Simple: calls backend.run()
        """
        backend = loader.get_backend(self)
        backend.run()

    def queue(self, name):
        """
        Get a unit queue by name.

        :returns: :class:`ShardedQueue` instance.
        :raises NotSavedError: Attempting to get a queue for a non-saved operation
        :raises NameError: Attempting to get an invalid queue
        """
        if name not in units.QUEUE_NAMES:
            raise NameError('%s is not a valid Operation queue name' % name)
        full_name = ':'.join(('units', str(self.key().id()), name))

        if name != 'active':
            return ShardedQueue(full_name, self.shard_count)
        else:
            scount = max(self.shard_count/2, 5)
            return ShardedCounter(full_name, scount)

    def clean(self):
        """
        Delete all queues for this Operation.

        This action cannot be undone; only use it if you know you don't need
        unit data for this operation!
        """
        for name in units.QUEUE_NAMES:
            self.queue(name).destroy()

    def errors(self, include_children=True):
        """
        Get a list of errors for this operation.

        :param include_children: Include the progress of all children? If
            ``True``, force this call up the sibling hierarchy until we get to
            the parent.
        :returns: Iterator over all errors
        """
        if include_children and self.parent_id:
            return self.find_parent().errors(True)

        children = []
        ours = UnitError.all().filter('op_id', self.key().id())
        if include_children:
            children = OperationMeta.all().filter('parent_id', self.key().id())

        return itertools.chain(ours, children)

    def progress(self, include_children=True):
        """
        Get the progress of this Operation.

        :param include_children: Include the progress of all children? If
            ``True``, force this call up the sibling hierarchy until we get to
            the parent.

        :return: Instance of :class:`Progress`.
        """
        from units import Progress

        if include_children and self.parent_id:
            return self.find_parent().progress(True)

        progress = defaultdict(list)
        progress['active'] = 0
        children = []

        if include_children:
            children = list(OperationMeta.all()\
                                         .filter('parent_id', self.key().id())\
                                         .fetch(1000))
        ops = children + [self]
        for op in ops:
            for queue_name in units.QUEUE_NAMES:
                queue = op.queue(queue_name)
                if queue_name != 'active':
                    items = queue.items()
                    if len(ops) > 1:
                        progress[queue_name].extend(items)
                    else:
                        progress[queue_name] = items
                else:
                    if len(ops) > 1:
                        progress[queue_name] =+ sum(queue.lazy_counter())
                    else:
                        progress[queue_name] = queue.lazy_counter()

        return Progress(progress.items())

    def child_of(self, op):
        """
        Sets this operation as the child of ``op``.

        :type op: :class:`OperationMeta`
        """
        oid = op.key().id()
        if not self.has_key() or oid != self.key().id():
            self.parent_id = oid
        return self

    def find_parent(self):
        """
        Find the parent of this operation, if any.
        """
        if not self.parent_id:
            return self
        return OperationMeta.get_by_id(self.parent_id).find_parent()

    def get_op_arg(self, key, default=None, decode=True):
        """
        Get an op arg via key.

        This interface mostly exists to interact with encoded values; for
        normal values, the :attr:`kwargs` property is preferred.
        """
        try:
            val = self.kwargs[key]
            if decode:
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return val
            return val
        except KeyError:
            return default

    def set_op_arg(self, key, val, encode=False):
        """
        Set a `self.next_chunk_args` `key` to `val`.

        New keys are added as necessary. The instance is also saved.

        :param encode: JSON-encode the value?
        """
        def txn(obj, k, v):
            obj = obj.reload()
            kw = obj.kwargs
            if encode:
                v = json.dumps(v)
            else:
                v = str(v)
            kw.update({ k: v })
            obj.args = list(itertools.chain(*kw.items()))
            obj.put()
            return obj

        if not self.is_saved():
            self.put()

        obj = db.run_in_transaction(txn, self, key, val)
        self.args = obj.args

    def as_email(self, val):
        return '@'.join((val, self.domain))

    def reload(self):
        return db.get(self.key())

    def get_json(self):
        """
        Get the JSON-decoded value for :attr:`json`.
        """
        if not self.json:
            return ''

        try:
            return self.__json
        except AttributeError:
            try:
                self.__json = json.loads(self.json)
            except Exception: # pickled :(
                self.__json = pickle.loads(self.json)

        return self.__json

    def set_json(self, value):
        """
        Set the JSON-encoded value for :attr:`json`.
        """
        try:
            self.json = json.dumps(value)
        except Exception:
            self.json = pickle.dumps(value)

    def composite_handler(self):
        """
        Build a CompositeHandler for this Operation.
        """
        handler_classes = loader.get_handlers(*self.handlers)
        return handlers.CompositeHandler(handler_classes, self)

    def is_complete(self, include_children=True):
        """
        Definitively determine if an Operation/Group is complete.

        This is different from "finished" in the sense that this method
        determines if the operation may be marked as finished. For groups
        (``children == True``), ``finished_on`` **is** checked. The rationale
        being, when you want to complete a Group, that information is relevant.

        :param include_children: Include children in determination?
        """
        for op in itertools.chain([self], include_children and self.children
                                  or []):
            if op != self and not op.finished_on:
                return False

            if op.queue('active').real_count() > 0:
                return False

            if op.queue('pending').count_greater_than(0):
                return False

        return True

    def clone(self, child=False):
        """
        Create a clone of the Operation. It is returned unsaved.

        :param child: Should it be a child operation?
        """

        op = self.__class__(handlers = self.handlers,
                           args = self.args,
                           json = self.json,
                           dmain = self.domain,
                           started_by = self.started_by)
        if child:
            op.child_of(self)

        return op

    def mk_cache_key(self, *args):
        """
        Generate a unique cache-qualified key.

        Key will look like: ``units:<id>:args[0]:...:args[n-1]``
        """
        prefix = [ 'units', str(self.key().id_or_name()) ]
        return ':'.join(prefix + [str(i) for i in args])

    @property
    def children(self):
        return self.all().filter('parent_id', self.key().id())

    @property
    def kwargs(self):
        """
        Supply the ``args`` field as a dictionary
        """
        from gapps import batch
        return dict(batch.utils.pair_up(self.args))

    data = property(get_json, set_json, doc='Get/set JSON using Python primitives')

    @property
    def is_slow(self):
        """
        The operation is taking a while to complete.
        """
        now = datetime.utcnow()
        delta = timedelta(hours=1)
        diff = now - self.created_on
        return not self.finished_on and diff > delta

    @property
    def maybe_stuck(self):
        """
        The operation has been going so long it may be stuck.
        """
        now = datetime.utcnow()
        delta = timedelta(hours=6)
        diff = now - self.created_on
        return not self.finished_on and diff > delta


class UnitError(BaseModel):
    """
    Errors that occur as a result of processing a work unit.

    :param key_name: <unit>|<op_id>
    """
    #: For filtering
    op_id = db.IntegerProperty()
    #: An arbitrary value that handlers should understand
    code = db.IntegerProperty(default=0)
    #: A descriptive error message
    msg = db.TextProperty(required=False, indexed=False)
    retries = db.IntegerProperty(default=0)
    last_error = db.DateTimeProperty(auto_now_add=True, auto_now=True)

    @classmethod
    def get_for(cls, unit, op, insert=True):
        """
        Get the associated UnitError for a [unit, op] combo or create
        a new one.

        :param save: Save to the database before returning?
        """
        oid = op.key().id()
        key_name = '%s|%d' % (unit, oid)
        if insert:
            return cls.get_or_insert(key_name, op_id=oid)
        else:
            return cls.get_by_key_name(key_name)

    def retrying(self):
        """
        Indicate this error is about to be retried.
        """
        self.retries += 1
        self.put()

    @classmethod
    def from_exc(cls, exc):
        """
        Create a UnitError record from a UnitError exception.
        """
        error = cls.get_for(exc.unit, exc.op)
        error.msg = exc.msg
        error.code = exc.code
        error.put()
        return error

    def __str__(self):
        unit, op = self.key().name().split('|')
        return 'Unit %s (OP#%s) failed (%d):\n%s' % (unit, op, self.code, self.msg)


class UnitDelay(BaseModel):
    """
    Track delays of individual units.

    :param key_name: <unit>|<op_id>
    """
    #: How many times this unit has been delayed
    delays = db.IntegerProperty(default=0)
    #: Current delay value in seconds
    current_delay = db.IntegerProperty(default=0, indexed=False)


class OperationStats(BaseModel):
    """
    Statistics for an Operation as stored in Memcache throughout a run.

    :param key_name: units:<parent_id>:<op_id>:stats
    """
    op_id = db.IntegerProperty(required=True)
    parent_id = db.IntegerProperty(default=0)
    #: Total number of tasks enqueued for the operation
    num_tasks_enqueued = db.IntegerProperty(default=0, indexed=False)
    #: All task runtimes, in seconds
    task_runtimes = db.ListProperty(float, indexed=False)

    def __init__(self, *args, **kwargs):
        if 'key_name' not in kwargs:
            kwargs['key_name'] = 'units:%d:%d:stats' % \
            (kwargs.get('parent_id', 0), kwargs['op_id'])

        super(OperationStats, self).__init__(*args, **kwargs)

