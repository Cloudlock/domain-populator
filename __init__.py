from __future__ import with_statement

import time
from datetime import datetime, timedelta
from functools import wraps
from inspect import getargspec, ismethod
from itertools import izip
from contextlib import contextmanager

from google.appengine.ext import db


def getcallargs(func, *args, **kwds):
    '''Get the actual value bounded to each formal parameter when calling
    `func(*args,**kwds)`.

    It works for methods too (bounded, unbounded, staticmethods, classmethods).

    @returns: `(bindings, missing_args)`, where:
        - `bindings` is a mapping of every formal parameter (including *varargs
           and **kwargs if present) of the function to the respective bounded value.
        - `missing_args` is a tuple of the formal parameters whose value was not
           provided (i.e. using the respective default value)

    Examples::
        >>> def func(a, b='foo', c=None, *x, **y):
        ...     pass
        >>> getcallargs(func, 5)
        ({'a': 5, 'y': {}, 'c': None, 'b': 'foo', 'x': ()}, ('b', 'c'))
        >>> getcallargs(func, 5, 'foo')
        ({'a': 5, 'y': {}, 'c': None, 'b': 'foo', 'x': ()}, ('c',))
        >>> getcallargs(func, 5, c=['a', 'b'])
        ({'a': 5, 'y': {}, 'c': ['a', 'b'], 'b': 'foo', 'x': ()}, ('b',))
        >>> getcallargs(func, 5, 6, 7, 8)
        ({'a': 5, 'y': {}, 'c': 7, 'b': 6, 'x': (8,)}, ())
        >>> getcallargs(func, 5, z=3, b=2)
        ({'a': 5, 'y': {'z': 3}, 'c': None, 'b': 2, 'x': ()}, ('c',))
    '''
    arg2value = {}
    f_name = func.func_name
    spec_args, varargs, varkw, defaults = getargspec(func)
    # handle methods
    if ismethod(func):
        # implicit 'self' (or 'cls' for classmethods) argument: func.im_self
        if func.im_self is not None:
            arg2value[spec_args.pop(0)] = func.im_self
        elif not args or not isinstance(args[0], func.im_class):
            got = args and ('%s instance' % type(args[0]).__name__) or 'nothing'
            raise TypeError('unbound method %s() must be called with %s instance '
                            'as first argument (got %s instead)' %
                            (f_name, func.im_class.__name__, got))
    num_args = len(args)
    has_kwds = bool(kwds)
    num_spec_args = len(spec_args)
    num_defaults = len(defaults or ())
    # get the expected arguments passed positionally
    arg2value.update(izip(spec_args,args))
    # get the expected arguments passed by name
    for arg in spec_args:
        if arg in kwds:
            if arg in arg2value:
                raise TypeError("%s() got multiple values for keyword "
                                "argument '%s'" % (f_name,arg))
            else:
                arg2value[arg] = kwds.pop(arg)
    # fill in any missing values with the defaults
    missing = []
    if defaults:
        for arg,val in izip(spec_args[-num_defaults:],defaults):
            if arg not in arg2value:
                arg2value[arg] = val
                missing.append(arg)
    # ensure that all required args have a value
    for arg in spec_args:
        if arg not in arg2value:
            num_required = num_spec_args - num_defaults
            raise TypeError('%s() takes at least %d %s argument%s (%d given)'
                            % (f_name, num_required,
                               has_kwds and 'non-keyword ' or '',
                               num_required>1 and 's' or '', num_args))
    # handle any remaining named arguments
    if varkw:
        arg2value[varkw] = kwds
    elif kwds:
        raise TypeError("%s() got an unexpected keyword argument '%s'" %
                        (f_name, iter(kwds).next()))
    # handle any remaining positional arguments
    if varargs:
        if num_args > num_spec_args:
            arg2value[varargs] = args[-(num_args-num_spec_args):]
        else:
            arg2value[varargs] = ()
    elif num_spec_args < num_args:
        raise TypeError('%s() takes %s %d argument%s (%d given)' %
                        (f_name, defaults and 'at most' or 'exactly',
                         num_spec_args, num_spec_args>1 and 's' or '', num_args))
    return arg2value, tuple(missing)


class DatastoreLockModel(db.Model):
    """
    Used by :class:`utils.DatastoreLock` context manager.

    A datastore representation of a lock / binary semaphore.  Used, for
    instance, to avoid modifying or cloning the same document simultaneously.
    """
    since = db.DateTimeProperty(required=True, auto_now_add=True)


class DatastoreLockTimeout(Exception):
    """Could not acquire lock in time."""


class DatastoreLock(object):
    """
    Context manager supporting generic Datastore-backed lock/ binary semaphore.

    Say you only want to clone a document once, but multiple tasks could
    try to do it simultaneously, circumventing some dupe checks. You could do
    this::

        with DatastoreLock('foo.com|document:123', timeout=5):
            clone('document:123')

    .. note::

       This particular example is better served by
       :class:`docutils.DocumentLock`, a simple subclass.

    If a lock cannot be acquired in ``timeout`` seconds,
    :class:`DatastoreLockTimeout` will be raised. This behavior is overridden by
    the ``silent`` argument.

    :param key_name: The unique name for this lock.
    :param timeout: Number of seconds to wait for lock
    :param sleep: Number of seconds to sleep between checks
    :param silent: Do not raise exception on lock failure

    """
    waited = 0.0
    lock = None
    #: Number of seconds to wait before giving up acquisition
    timeout = 0
    #: Model used to represent the lock in the Datastore
    lockModel = DatastoreLockModel
    #: Constructed to uniquely identify the lock
    key_name = None
    #: Number of seconds to sleep between acquisition attempts
    sleep = None
    #: Fail silently when we can't acquire lock?
    silent = False
    #: Maximum number of seconds a lock can be held for
    ttl = 60 * 60

    def __init__(self, key_name, rid=None, timeout=30, sleep=0.5,
                 silent=False):
        self.timeout = timeout
        self.key_name = key_name
        self.sleep = sleep
        self.silent = silent

    def __enter__(self):
        """
        Attempt to acquire lock.
        """
        while True:
            lock = None
            try:
                lock = db.run_in_transaction(self.txn_acquire_lock)
            except db.TransactionFailedError:
                # We pass, allowing another try
                pass
            if lock:
                self.lock = lock
                break
            elif self.waited < self.timeout:
                self.waited += self.sleep
                time.sleep(self.sleep)
            else:
                break
        if not self.lock and not self.silent:
            raise DatastoreLockTimeout()

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Ensure lock is released regardless of exception.
        """
        if self.lock is not None:
            self.lock.delete()

    def mk_lock(self):
        """
        Make (but do not save) a datastore lock entity.
        """
        return self.lockModel(key_name=self.key_name)

    def txn_acquire_lock(self):
        """
        Transactionally acquire a unique lock (we created it or it expired)

        :returns: The DatastoreLock (model) object, or None if acquisition failed
        """
        now = datetime.now()
        ttl = timedelta(seconds=self.ttl)
        acquired = self.lockModel.get_by_key_name(self.key_name)
        if acquired is None:
            lock = self.mk_lock()
            lock.since = now
            lock.put()
            return lock
        elif acquired.since + ttl < now:
            acquired.since = now
            acquired.put()
            return acquired
        return None


def with_lock(key_fmt):
    """
    A decorator used to run a function IFF a lock can be acquired.

    If the lock cannot be acquired, the decorator will raise
    ``DatastoreLockTimeout`` as is expected from the standard ``DatastoreLock``
    context manager.

    :param key_fmt: A format string whos named expansion variables are
        populated by the arguments supplied to the decorated fuction. For
        instance, if the decorated function takes an argument ``foo``, this
        value could be something like ``'unique_for_%(foo)s'``.
    """
    def wrap(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            argdict, _ = getcallargs(func, *args, **kwargs)
            d = argdict
            d.update(argdict.get('kwargs', {}))
            key_name = key_fmt % d
            with DatastoreLock(key_name, timeout=0):
                return func(*args, **kwargs)
        return wrapper
    return wrap


@contextmanager
def transaction(fn, *args, **kwargs):
    """
    Context manager; ensures a transaction succeeds and returns Non-None before
    running its block.
    """
    txn = None
    try:
        txn = db.run_in_transaction(fn, *args, **kwargs)
    except db.TransactionFailedError:
        pass
    yield txn


def aclmod_to_admin_action(entry):
    """
    Since AdminAction is so retarded, I do extra work to convert an ACL entry
    into an arbitrary action string.
    """
    action = entry['action'] 

    # An assumption about what 'publish_remove' even means
    if action == 'rm' and entry['type'] in ('domain', 'default'):
        return 'publish_remove'

    elif action == 'rm':
        return 'acl_remove'

    # This is actually not necessarily true, but whatever. Assuming 'acl_owner'
    # means 'changed the owner'.
    if entry['role'] == 'owner' and action == 'mod':
        return 'acl_owner'

    for role, label in (('reader', 'read'), ('writer', 'write')):
        if entry['role'] == role:
            if action == 'add':
                return 'acl_%s_add' % label
            elif action == 'mod':
                return 'acl_%s' % label


if __name__ == '__main__':
    import doctest
    doctest.testmod()

