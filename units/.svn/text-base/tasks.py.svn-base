from __future__ import absolute_import, with_statement

import time
import logging
import random
from functools import wraps

from django.http import HttpResponse
from google.appengine.api import memcache
from google.appengine.ext import db
from gapps.decorators import taskqueue_only

from units import runner, loader
from units.models import OperationMeta


def cache_runtime(func):
    """
    Record time taken to run a task in memcache for later persistent storage.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        before = time.time()
        result = func(*args, **kwargs)
        diff = time.time() - before

        if isinstance(result, HttpResponse):
            try:
                oid = int(result.content)
            except ValueError:
                pass
            else:
                count_key = 'units:%d:task_runtimes_counted' % oid
                incremented = memcache.incr(count_key, initial_value=0)
                if incremented is not None:
                    time_key = 'units:%d:task_runtime_%d' % (oid, incremented)
                    memcache.set(time_key, diff)
        return result
    return wrapped


@cache_runtime
@taskqueue_only
def run(request, taskinfo, oid):
    """
    Run an operation. May be called multiple times on error.

    :raises: Re-raises anything caught during prerun() callback; relies on
        TaskQueue and decorator logic to delay and limit retries.
    """
    op = get_or_log(oid, 'run')
    if op:
        runner.try_operation(op)

        return HttpResponse(str(op.key().id()))
    return HttpResponse('Operation Gone.')


@cache_runtime
@taskqueue_only
def sync(request, taskinfo, oid):
    """
    Sync an operation's queues.

    :raises ValueError: If a unit cannot be found to remove.
    """
    unit = request.raw_post_data

    op = get_or_log(oid, 'sync')
    if op:
        op.sync(unit)

        return HttpResponse(str(op.key().id()))
    return HttpResponse('Operation Gone.')


@cache_runtime
@taskqueue_only
def active(request, taskinfo, oid):
    """
    Unit is "active" (being worked).
    """
    unit = request.raw_post_data

    op = get_or_log(oid, 'run unit %s of' % unit)
    if op:
        runner.try_unit(op, unit)

        # Support units.backends.CountingMixin
        backend = loader.get_backend(op)
        try:
            backend.task_returning()
        except AttributeError: # No mixin
            pass
        # End units.backends.CountingMixin support

        return HttpResponse(str(op.key().id()))
    return HttpResponse('Operation Gone.')


@cache_runtime
@taskqueue_only
def finish_op(request, taskinfo, oid):
    """
    Operation is being finished.
    """
    op = get_or_log(oid, 'finish')
    if op:
        updated_op = runner.finish_op(op)

        # If we couldn't finish in this process there's a chance we'll never
        # finish; re-attempt the finish with a delay. If we can't finish after
        # a few tries, it probably means there's an orphaned unit.
        if not updated_op.finished_on:
            backend = loader.get_backend(op)
            if op.finish_attempts > 3:
                backend.next()
            try:
                db.run_in_transaction(txn_finish_attempts, oid)
            finally:
                backend.finish_op(delay=random.randint(1, 10))

        return HttpResponse(str(op.key().id()))
    return HttpResponse('Operation Gone.')


@cache_runtime
@taskqueue_only
def finish_group(request, taskinfo, oid):
    """
    Operation is being finished.
    """
    op = get_or_log(oid, 'finish grouped')
    if op:
        # Always work with the parent operation
        op = op.find_parent()
        updated_op = runner.finish_group(op)

        # If we couldn't finish in this process there's a chance we'll never
        # finish; re-attempt the finish with a delay. Logic for avoiding zombie
        # operations is handled by finish_op().
        if not updated_op.group_finished_on:
            backend = loader.get_backend(op)
            backend.finish_group(delay=random.randint(1, 10))

        return HttpResponse(str(op.key().id()))
    return HttpResponse('Operation Gone.')


def txn_finish_attempts(oid):
    op = OperationMeta.get_by_id(int(oid))
    op.finish_attempts += 1
    op.put()
    return op


def get_or_log(oid, step):
    oid = int(oid)
    op = OperationMeta.get_by_id(oid)
    if not op:
        logging.error('Cannot %s Operation #%s; does not exist', step, oid)
    return op

