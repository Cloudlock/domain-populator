from __future__ import with_statement

import time
import logging
import random
from datetime import datetime

from django.conf import settings
from django.core.urlresolvers import reverse
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from utils import transaction

from units import runner
from units.exc import TooManyDelays, OperationActive
from units.models import OperationMeta, UnitDelay


class BaseBackend(object):
    """
    Backend API definition for handling Operation work.

    This basic backend performs all work immediately when called and lacks any
    super powers.

    :ivar op: :class:`OperationMeta` instance this backend instance serves.
    """
    #: Max delays per Operation
    max_op_delays = 10
    #: Max delays per Unit (separate)
    max_unit_delays = 5
    #: Does this backend behave asynchronously?
    async = False

    def __init__(self, op):
        self.op = op
        self.oid = op.key().id()
        self.delay_key = self.op.mk_cache_key('delay')

        # Map over handler overrides
        data = self.op.data
        if isinstance(data, dict):
            overrides = data.get('backend_attrs', {})
            for attr, value in overrides.items():
                setattr(self, attr, value)

    def run(self):
        """
        Run an Operation.
        """
        runner.try_operation(self.op)

    def bulk_do(self, units, delay=0, **kwargs):
        """
        Run a bunch of units at once.

        By default, this method doesn't do anything special; it simply calls
        :meth:`do_unit`. However, some backends are more robust when they can
        update counters and such in bulk rather than per-unit.
        """
        results = []
        for unit in units:
            results.append(self.do_unit(unit, delay, **kwargs))
        return any(results)

    def do_unit(self, unit, delay=0, **kwargs):
        """
        Run ``unit``.

        :param unit: Work unit to perform
        :param delay: Number of seconds to delay the run
        :returns: Boolean indicating if the unit just passed is now complete
        """
        self.op.queue('active').incr()
        runner.try_unit(self.op, unit)
        return True

    def finish_op(self, delay=0, **kwargs):
        """
        Finish an Operation.

        Takes same arguments as :meth:`do_unit`, minus ``unit``.
        """
        runner.finish_op(self.op)
        self.op = self.op.reload()

        # If we couldn't finish in this process and we're an async backend,
        # there's a chance we'll never finish; raise an exception as a warning.
        if not self.op.finished_on and self.async:
            raise OperationActive('OP #%d is still active!' % self.oid)

    def finish_group(self, delay=0, **kwargs):
        """
        Finish an Operation Group.

        Takes same arguments as :meth:`do_unit`, minus ``unit``.
        """
        runner.finish_group(self.op)
        self.op = self.op.reload()

        # If we couldn't finish in this process and we're an async backend,
        # there's a chance we'll never finish; raise an exception as a warning.
        if not self.op.group_finished_on and self.async:
            raise OperationActive('OP group #%d is still active!' % self.oid)

    def next(self, *args, **kwargs):
        """
        Find another unit of work to perform.

        Takes the same arguments as :meth:`do`, minus ``unit`` of course.

        :returns: True if another unit was available; False otherwise.
        """
        unit = self.op.queue('pending').pop()
        if unit is not None:
            self.do_unit(unit, *args, **kwargs)
            return True
        return False

    def sync(self, unit, delay=0, **kwargs):
        """
        Synchronize operaton queues.

        Race conditions among transactions can cause queues to get de-synced;
        e.g., an item is transactionally added to the active queue but an
        attempt is made to remove it before the transaction commits. In cases
        such as these, we need to re-sync or risk creating a stuck operation.
        """
        self.op.sync(unit)

    def compute_delay(self, count, isunit=False):
        """
        Compute number of seconds to delay work, based on ``count`` delays.

        By default, uses an exponential-ish time increase based on how many
        previous delays have happened for the operation this backend instance
        serves.

        :param isunit: Are we delaying a unit? By default, doesn't matter.
        """
        return 1 + (2 * max(1, count)) + random.randint(5,15)

    def delay(self, secs=None, expires=60):
        """
        Delay work across this backend.

        :param expires: How long the delay should stay in effect
        :returns: Boolean based on whether or not this instance successfully
            delayed. The delay is guaranteed atomic meaning another backend
            instance for this operation may have already delayed it.
        """
        def txn(current_delays, delay):
            op = OperationMeta.get_by_id(self.oid)
            if op.delays == current_delays:
                op.delays += 1
                op.current_delay = delay
                op.put()
                return True
            return False
        
        if self.op.delays >= self.max_op_delays:
            raise TooManyDelays()

        # Already delayed; do not increase until current expires.
        if memcache.get(self.delay_key):
            return True

        delays_now = self.op.delays
        delay = secs or self.compute_delay(delays_now)

        with transaction(txn, delays_now, delay) as result:

            if not result:
                logging.warn('Operation #%d already delaying.' % self.oid)
                return

            self.op = self.op.reload()

            logging.info('Backend for Operation #%d delaying work for %d seconds (%d/%d)',
                         self.oid, delay, delays_now, self.max_op_delays)
            memcache.add(self.delay_key, (delays_now+1, secs), expires)
            return result

        return False

    def delay_unit(self, unit, secs=None, expires=60):
        """
        Delay work on a unit.

        :returns: Boolean based on whether or not this instance successfully
            delayed. The delay is guaranteed atomic meaning another backend
            instance for this operation may have already delayed it.
        """
        key_name = '%s|%d' % (unit, self.oid)
        ud = UnitDelay.get_or_insert(key_name)

        # Already delayed; do not increase until current expires.
        if memcache.get(self.unit_delay_key(unit)):
            return True

        if ud.delays >= self.max_unit_delays:
            raise TooManyDelays()

        def txn(current_delays, delay):
            ud = UnitDelay.get_by_key_name(key_name)
            if ud.delays == current_delays:
                ud.delays += 1
                ud.current_delay = delay
                ud.put()
                return True
            return False

        delays_now = ud.delays
        delay = secs or self.compute_delay(delays_now, True)

        with transaction(txn, delays_now, delay) as result:
            if result:
                logging.info('Backend for Operation #%d delaying work on unit %s '
                             'for %d seconds', self.oid, unit, delay)
                memcache.add(self.unit_delay_key(unit), (delays_now+1, secs), expires)
            return result

        return False

    def get_delay(self, unit=None):
        """
        Figure out how long to delay something, based on current state.

        For units, a unit delay takes precedent. Otherwise, the Operation
        delay is applied.
        """
        delay_info = None

        if unit is not None:
            delay_info = memcache.get(self.unit_delay_key(unit))

        if delay_info is None:
            delay_info = memcache.get(self.delay_key)

        if delay_info is not None:
            delay_count, hard_count = delay_info
            return hard_count or self.compute_delay(delay_count)

        return 0

    def remove_delay(self, unit=None):
        """
        Remove a delay for an Operation or unit.

        Usually called following a success.
        """
        key_name = self.delay_key if unit is None else self.unit_delay_key(unit)
        memcache.delete(key_name)

    def unit_delay_key(self, unit):
        return self.op.mk_cache_key('delay', unit)


class CountingMixin(object):
    """
    Will maintain a running count of tasks in the Datastore, maintaining
    concurrency limits across runs at the expense of performance.

    It makes a best-effort attempt to adhere to the defined concurrency level,
    though race conditions do exist which preclude it from being a guarantee.
    """
    def bulk_do(self, units, delay=0, **kwargs):
        """
        Increment memcache counters in bulk to help reset issues.
        """
        handlers = self.op.composite_handler()
        concurrency = max(handlers.attr('concurrency', 1))
        delta = len(units)

        new_val = memcache.incr(self.counter, delta=delta, initial_value=0)
        todo = concurrency - ((new_val or delta) - delta - 1)
        for x in xrange(todo):
            try:
                super(CountingMixin, self).do_unit(units.pop(), delay, **kwargs)
            except IndexError:
                break
        for unit in units:
            self.op.queue('pending').add(unit)

        return todo > 0

    def do_unit(self, unit, *args, **kwargs):
        """
        Ensure running count of active jobs doesn't exceed desired concurrency.
        """
        handlers = self.op.composite_handler()
        concurrency = max(handlers.attr('concurrency', 1))

        # We do -1 here because backend.next() will call do_unit() before the
        # task hits task_returning(), so the number is always off by one...
        # Unless there isn't a next unit, in which case who cares?!
        cached = memcache.get(self.counter)
        count = int(cached or 0)
        if count - 1 < concurrency:
            memcache.incr(self.counter, initial_value=0)
            return super(CountingMixin, self).do_unit(unit, *args, **kwargs)
        else:
            self.op.queue('pending').add(unit)
            return False

    def task_returning(self):
        cached = memcache.get(self.counter)
        if cached is None or cached > 0:
            memcache.decr(self.counter, initial_value=0)

    def finish_group(self, *args, **kwargs):
        """
        Get rid of our counter entities; operation is finishing.
        """
        memcache.delete(self.counter)
        return super(CountingMixin, self).finish_group(*args, **kwargs)

    @property
    def counter(self):
        """
        Fetch a counter instance with 5 shards.
        """
        return '|'.join(('units', 'cm', str(self.op.key().id())))


class PushQueueBackend(BaseBackend):
    """
    Backend which uses Google AppEngine Push queues.

    Operations may provide oparg ``queue`` to define the default queue.
    """
    async = True

    DEFAULT_QUEUE = 'docreport-apicalls'

    def run(self, delay=0, transactional=False, queue=None):
        """
        Push run onto the taskqueue.
        """
        delay = delay or self.get_delay()
        queue = queue or self.get_queue()
        uri = reverse('units:task-run',
                      kwargs={ 'oid': self.oid })
        task = taskqueue.Task(url=uri, countdown=delay)
        task.add(transactional=transactional, queue_name=queue)

    def do_unit(self, unit, delay=0, transactional=False, queue=None):
        """
        Push an active task onto the taskqueue.

        :param transactional: Is this task being queued transactionally?
        :param queue: The queue name to use (or ``self.DEFAULT_QUEUE``)
        :param delay: Custom delay; will be computed based on existing
            environment.
        """
        self.op.queue('active').incr()
        delay = delay or self.get_delay(unit)
        queue = queue or self.get_queue()
        uri = reverse('units:task-active', kwargs={ 'oid': self.oid })
        task = taskqueue.Task(url=uri, countdown=delay, payload=unit)
        task.add(transactional=transactional, queue_name=queue)
        memcache.incr(self.op.mk_cache_key('num_tasks_enqueued'),
                      initial_value=0)
        memcache.set(self.op.mk_cache_key('last_unit_enqueue'),
                     datetime.utcnow())
        return False

    def sync(self, unit, delay=0, transactional=False, queue=None):
        queue = queue or self.get_queue()
        uri = reverse('units:task-sync', kwargs={ 'oid': self.oid })
        self._enqueue_named('sync', uri, delay, queue, unit)

    def finish_op(self, delay=0, transactional=False, queue=None):
        """
        Finish an Operation.

        :param transactional: Is this task being queued transactionally?
        :param queue: The queue name to use (or ``self.DEFAULT_QUEUE``)
        :param delay: Custom delay; will be computed based on existing
            environment.
        """
        delay = delay or self.get_delay()
        queue = queue or self.get_queue()
        uri = reverse('units:task-finish-op',
                      kwargs={ 'oid': self.oid })
        self._enqueue_named('finish_op', uri, delay, queue, None)
        return False

    def finish_group(self, delay=0, transactional=False, queue=None):
        """
        Finish an Operation Group.

        :param transactional: Is this task being queued transactionally?
        :param queue: The queue name to use (or ``self.DEFAULT_QUEUE``)
        :param delay: Custom delay; will be computed based on existing
            environment.
        """
        delay = delay or self.get_delay()
        queue = queue or self.get_queue()
        uri = reverse('units:task-finish-group',
                      kwargs={ 'oid': self.oid })
        self._enqueue_named('finish_group', uri, delay, queue, None)
        return False

    def get_queue(self):
        return self.op.kwargs.get('queue', self.DEFAULT_QUEUE)

    def _enqueue_named(self, name, uri, countdown, queue, payload):
        task_name = self.op.mk_cache_key(name).replace(':', '-')
        task = taskqueue.Task(url=uri, countdown=countdown, payload=payload,
                              name=task_name)
        try:
            task.add(transactional=False, queue_name=queue)
        except taskqueue.TaskAlreadyExistsError:
            pass
        except taskqueue.TombstonedTaskError:
            future = (int(time.time()) / 3)
            task_name += '-%d' % future
            countdown += (3 - countdown) if countdown < 3 else 0
            task = taskqueue.Task(url=uri, countdown=countdown,
                                  payload=payload, name=task_name)
            try:
                task.add(transactional=False, queue_name=queue)
            except (taskqueue.TaskAlreadyExistsError,
                    taskqueue.TombstonedTaskError):
                pass
        else:
            memcache.incr(self.op.mk_cache_key('num_tasks_enqueued'),
                          initial_value=0)


class CountingPushQueueBackend(CountingMixin, PushQueueBackend):
    """
    I use a simple PushQueue and the CountingMixin to pseudo-guarantee
    concurrency across multiple operation runs.
    """
    pass


class BalancedPushQueueBackend(PushQueueBackend):
    """
    I balance requests across a number of AppEngine Push Queues.

    Operations may provide oparg ``queues`` to define the Operation's queue set
    which should be a JSON-parsable list of queue names. (Hint: use
    :meth:`OperationMeta.set_op_arg` to get free encoding)
    """
    def __init__(self, *args, **kwargs):
        super(BalancedPushQueueBackend, self).__init__(*args, **kwargs)
        default_queues = ['docreport-apicalls' + s for s in
                          settings.QUEUE_SUFFIXES]
        self.QUEUES = self.op.get_op_arg('queues', default_queues)

    def get_queue(self):
        return random.choice(self.QUEUES)

