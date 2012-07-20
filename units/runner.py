from __future__ import with_statement

import logging
import traceback
from datetime import datetime

from gdata.client import RequestError
from google.appengine.ext import db

from utils import transaction

from units import loader
from units.exc import DelayUnit, DelayOperation, UnitError, TooManyDelays
from units.models import OperationMeta
from units.models import UnitError as UnitErrorModel


def convert(s):
    """
    Attempt to convert a value to Blob if necessary; fallback to unicode()
    """
    if not isinstance(s, basestring):
        try:
            return db.Blob(s)
        except TypeError:
            return unicode(s)
    return s


def try_operation(op):
    """
    Run an operation. May be called multiple times on error.

    :raises: Any exception encountered during :meth:`prerun()` callback.
    """
    oid = op.key().id()
    def incr_run_count():
        upop = op.reload()
        upop.run_count += 1
        if not upop.started_on:
            upop.started_on = datetime.now()
        upop.put()
        return upop

    with transaction(incr_run_count) as op:
        if not op:
            logging.warn('Operation #%d already running; stopping.' % oid)
            return

        backend = loader.get_backend(op)
        handlers = op.composite_handler()
        log = handlers[0].log
        max_runs = max(handlers.attr('max_runs', 1, int))
        concurrency = max(handlers.attr('concurrency', 1, int))
        had_unit = False
        running = 0
        pending = op.queue('pending')

        # Count pre-incremented
        if op.run_count-1 < max_runs:
            try:
                handlers.call('prerun')
            except Exception:
                msg = ('Exception during pre-run (attempt %d):\n%s' %
                       (op.run_count, traceback.format_exc()))
                log.error(msg)
                op.put()
                raise
            else:
                iterators = handlers.call('iterunits')
                while len(iterators) > 0:
                    unit = None
                    for i in iterators:
                        try:
                            unit = i.next()
                            if unit is None:
                                continue

                            if isinstance(unit, OperationMeta):
                                had_unit = True
                                loader.get_backend(unit).run()
                                continue

                            unit = convert(unit)

                            if running < concurrency or not backend.async:
                                had_unit = True
                                ran = backend.do_unit(unit)
                                if not ran:
                                    running += 1
                            else:
                                pending.add(unit)

                        except StopIteration:
                            iterators.remove(i)

                # Empty operations
                if not had_unit:
                    backend.finish_op()
                    backend.finish_group()

        else:
            try:
                handlers.call('op_failed')
            except Exception:
                msg = ('Exception during op_failed():\n%s' %
                       traceback.format_exc())
                log.error(msg)

            op.failed_on = datetime.now()
            op.put()
            log.error('Failed to run; giving up.')


def try_unit(op, unit, single=False, adhoc=False, **kwargs):
    """
    Attempt to work a unit.

    :param single: Run only this unit; do not attempt to enqueue others
    :param adhoc: This is an adhoc run; don't worry about de-sync, etc.
    """
    unit = convert(unit)
    success = False
    done_val = None
    has_next = False
    retrying = False

    backend = loader.get_backend(op)
    handlers = op.composite_handler()
    log = handlers[0].log
    delay_choices = handlers.attr('finish_delay', 0, int)
    delay = max(delay_choices)
    delay_codes = handlers.attr('delay_codes', cast=int)

    if not backend.async:
        op.queue('active').incr()

    try:
        try:
            retval = filter(lambda r: r is not None, handlers.call('do_unit', unit))
            if retval:
                try:
                    done_val = convert(retval[0])
                except Exception: # cannot convert to unicode; ignore...
                    pass
            success = True

        except (DelayUnit, DelayOperation):
            raise

        except Exception, e:
            err = normalize_exc(e, unit, op)
            if err.code in delay_codes and (err.code * -1) not in delay_codes:
                raise DelayOperation()
            try:
                handlers.call('unit_error', unit, err)
                success = True
            except Exception:
                raise

        finish_unit(op, unit, done_val or unit)

    except DelayUnit, d:
        has_next = delay_unit(op, unit, d)
        retrying = has_next

    except DelayOperation, d: 
        has_next = delay_unit(op, unit, d)
        retrying = has_next

    except Exception, e:
        err = normalize_exc(e, unit, op)
        has_next = err_unit(op, unit, err)
        retrying = has_next

    finally:
        # Remove from active queue
        op.queue('active').decr()
        # Callback: unit_done()
        try:
            handlers.call('unit_done', unit, success, retrying)
        except Exception, e:
            log.error('unit_done(%s) raised:\n%s' %
                      (unit, traceback.format_exc()))
        # Async backends must have next() called manually
        if backend.async and not single and not adhoc:
            has_next = backend.next()
        # Handle possible Operation completion
        if has_next == False or not backend.async:
            backend.finish_op(delay=delay)
            backend.finish_group(delay=delay)


def finish_unit(op, unit, newval):
    """
    Finish a unit: move to "done" queue and tell backend to start the next one.
    """
    backend = loader.get_backend(op)
    backend.remove_delay()
    backend.remove_delay(unit)
    error = UnitErrorModel.get_for(unit, op, False)
    if error is not None:
        error.delete()
    op.queue('done').add(newval)


def finish_op(op):
    """
    Finish an Operation, calling appropriate callbacks.

    :raises: Any exception encountered in :meth:`op_done`
    :raises OperationActive: If the Operation isn't really finished
    """
    def finish():
        meta = op.reload()
        if not meta.finished_on:
            meta.finished_on = datetime.now()
            meta.put()
            return meta

    def unfinish():
        meta = op.reload()
        if meta.finished_on:
            meta.finished_on = None
            meta.put()
            return meta

    handlers = op.composite_handler()
    log = handlers[0].log

    # If I can see that this has been finished with a single read, I'd much
    # rather do that than find out after all the queue counts have been taken.
    if op.reload().finished_on:
        return op

    if op.is_complete(False):
        with transaction(finish) as result:

            if not result:
                log.warn('Finishing in another process.')
                return op

            handlers.set('meta', result)
            try:
                handlers.call('op_done')
            except Exception:
                log.error('op_done(%s) raised:\n%s' %
                          (op.key().id(), traceback.format_exc()))
                db.run_in_transaction(unfinish)
                raise
            return result
    return op


def finish_group(op):
    """
    Finish an Operation group, calling appropriate callbacks.

    :param op: The **parent** Operation
    :raises: Any exception encountered in :meth:`group_done`
    :raises OperationActive: If the Operation isn't really finished
    """
    # Make sure we always consult the parent operation; backend should handle
    # this for us, though.
    op = op.find_parent()

    def finish():
        meta = op.reload()
        if not meta.group_finished_on:
            meta.group_finished_on = datetime.now()
            meta.put()
            return meta

    def unfinish():
        meta = op.reload()
        if meta.group_finished_on:
            meta.group_finished_on = None
            meta.put()
            return meta

    handlers = op.composite_handler()
    log = handlers[0].log

    # If I can see that this has been finished with a single read, I'd much
    # rather do that than find out after all the queue counts have been taken.
    if op.reload().group_finished_on:
        return op

    if op.is_complete():
        with transaction(finish) as result:

            if not result:
                log.warn('Finishing group in another process.')
                return op

            handlers.set('meta', result)
            try:
                handlers.call('group_done')
            except Exception:
                log.error('group_done(%s) raised:\n%s' %
                          (op.key().id(), traceback.format_exc()))
                db.run_in_transaction(unfinish)
                raise
            return result
    return op


def err_unit(op, unit, exc):
    """
    Unit is in error state. Record and retry, if warranted.

    :param exc: Expected to be exception of :class:`UnitError`
    :returns: True if the unit will be retried
    """
    has_next = True
    handlers = op.composite_handler()
    retry_max = handlers[0].retry_max
    noretry_codes = handlers.attr('noretry_codes', cast=int)
    log = handlers[0].log

    error = UnitErrorModel.from_exc(exc)

    if error.retries < retry_max and error.code not in noretry_codes:
        error.retrying()
        op.queue('pending').add(unit)
        log.warn('Unit "%s" queued for retry #%d.' % (unit, error.retries))
    else:
        if error.code in noretry_codes:
            log.warn('Unit "%s" failed; not retrying code %s.' %
                     (unit, error.code))
        else:
            log.warn('Unit "%s" failed %d time(s); giving up.' %
                     (unit, error.retries))

        has_next = False
        log.error(error)
        op.queue('error').add(unit)

    return has_next


def delay_unit(op, unit, exc):
    """
    Delay a unit.

    :param exc: Instance of :class:`OperationDelay` or :class:`UnitDelay`
    """
    handlers = op.composite_handler()
    log = handlers[0].log
    backend = loader.get_backend(op)
    is_op = isinstance(exc, DelayOperation)

    try:
        try:
            handlers.call('unit_delay', unit, is_op)
        except TooManyDelays:
            raise
        except Exception:
            log.error('unit_delay(%s) raised:\n%s' %
                      (unit, traceback.format_exc()))

        if is_op:
            result = backend.delay(exc.delay)
        else:
            result = backend.delay_unit(unit, exc.delay)

        if result == True:
            op.queue('pending').add(unit)

        return True

    except TooManyDelays:
        log.warn('Delayed too many times; giving up.')
        op.queue('skipped').add(unit)
        return False


def normalize_exc(exc, unit, op):
    """
    Normalize any exception to an instance of :class:`UnitError`.

    Special handling of :class:`RequestError`.
    """
    tb = traceback.format_exc()

    if isinstance(exc, RequestError):
        err = UnitError(unit=unit, op=op, req=exc, tb=tb)
    else:
        err = UnitError(unit=unit, op=op, msg=tb)

    return err

