import itertools
import types

from google.appengine.ext import db

from units.models import OperationMeta
from units.loader import validate_handler


QUEUE_NAMES = ( 'pending', 'active', 'done', 'skipped', 'error' )


class Progress(dict):
    """
    Provides lazy access to Operation queue item counts and other progress.

    Progress provides a lazy interface with the below specification. As it is a
    dictionary subclass, it "caches" its values, so retreiving a known value
    will **not** access the Datastore.

    :cvar total: ``<total unit count>``
    :cvar num_done_or_error: ``<done+skipped+error>``
    :cvar num_*: ``<pending, active, done, skipped, or error>``
    :cvar progress_pct: Percentage complete based on current counts
    """
    def __new__(cls, *args, **kwargs):
        lazy_names = ['progress_pct', 'num_done_or_error', 'num_total']
        lazy_names.extend(['num_'+name for name in QUEUE_NAMES])
        obj = dict.__new__(cls, *args, **kwargs)
        obj.lazy_names = lazy_names
        return obj

    def num(self, name):
        if name == 'total':
            return sum((self.num(n) for n in QUEUE_NAMES))
        elif name == 'done_or_error':
            return sum((self.num(n) for n in QUEUE_NAMES[2:]))

        if isinstance(self[name], (types.GeneratorType, itertools.chain)):
            if name == 'active':
                self[name] = sum(self[name])
            else:
                self[name] = list(self[name])

        try:
            return len(self[name])
        except TypeError:
            return self[name]

    def __getattr__(self, name):
        if name in self.lazy_names:
            if name == 'progress_pct':
                total = self.num('total')
                done_or_error = self.num('done_or_error')
                if total:
                    return int(100 * done_or_error / float(total))
                else:
                    return 100
            else:
                return self.num(name[4:])

        return self.__getitem__(name)


def operation(handlers, domain=None, opargs=None,
              backend='units.backends.PushQueueBackend',
              spec=None, child=True):
    """
    Helper function for creating Operations.

    :param handlers: One or more handler dotpaths (includes validation)
    :type handlers: string or list
    :param opargs: Operation-level arguments to store for use during run
    :type opargs: dict
    :param backend: Dotpath to custom backend
    :param spec: Base the operation on an existing :class:`OperationMeta`
    :param child: If ``spec`` is given, should the result be a child operation?
    """
    args = []

    if isinstance(handlers, basestring):
        handlers = [handlers]

    for handler in handlers:
        validate_handler(handler)

    if opargs:
        args = list(itertools.chain(*opargs.items()))
        args = [unicode(i) for i in args]
    if spec:
        op = spec.clone(child)
    else:
        op = OperationMeta()

    op.domain = domain
    op.handlers = handlers
    op.backend = backend
    op.args=args
    op.put()
    return op


def bootstrap(op, units, last=False):
    """
    Bootstrap an operation run by supplying a list of units.

    Each time this is called, the unit list will be refreshed, the operation
    will be ran, and the unit list will be emptied (via handler). This function
    is thread-safe.

    :param op: :class:`OperationMeta` instance to bootstrap
    :param units: The units to work
    :type units: list/tuple/etc
    :param last: Indicate this is the last group of units to be processed;
        remove finish delay
    """
    def set_units(u):
        o = op.reload()
        existing = o.data
        if not isinstance(existing, dict):
            existing = {}
        if 'bootstrap_units' not in existing:
            existing['bootstrap_units'] = []
        existing['bootstrap_units'].extend(u)
        o.data = existing
        o.put()
        return o

    def set_finish_delay(delay):
        o = op.reload()
        o.set_op_arg('finish_delay', delay, True)
        o.put()
        return o

    op = db.run_in_transaction(set_units, units)
    if last:
        set_finish_delay(0)
    op.start()

