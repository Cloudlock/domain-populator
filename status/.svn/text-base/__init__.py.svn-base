import random
from datetime import datetime

from gapps.batch.handlers import BaseHandler as BatchBaseHandler
from units.handlers import BaseHandler as UnitsBaseHandler
from status.models import Operation, OperationSet, ExpiredClientError


class Messenger(object):
    """
    A friendlier interface to :class:`status.models.Subscriber`.

    Use this class to send operation status updates to subscribed clients and
    keep operations in sync between the backend and frontend.
    """
    #: OperationSet instance
    opset = None
    #: Active operation
    active_operation = ''

    def __init__(self, model=None, domain='', namespace=None, ids=None):
        if ids is None:
            ids = []

        if model:
            if isinstance(model, OperationSet):
                self.opset = model
                return
            namespace, ids = self.model_to_meta(model)
            self.active_operation = self.compute_oid(namespace, ids)

        if not isinstance(ids, (tuple, list, set)):
            self.active_operation = self.compute_oid(namespace, ids)
            ids = [ids]

        oids = [ self.compute_oid(namespace, i) for i in ids ]
        self.opset = OperationSet.get_or_create(oids, domain)

    @staticmethod
    def compute_oid(ns, oid):
        """
        Create an operation ID; a simple join.
        """
        return ':'.join([ str(x) for x in (ns, oid) ])

    @staticmethod
    def model_to_meta(model):
        """
        Extract a namespace and ID from a saved model instance.
        """
        try:
            namespace = model.__class__.__name__
            ids = str(model.key().id() or model.key().name())
        except Exception:
            raise ValueError('`model` must be a valid, saved datastore '
                             'object.')
        return (namespace, ids)

    @classmethod
    def model_to_oid(cls, model):
        """
        Convert a model instance directly to an Operation key name.
        """
        return cls.compute_oid(*cls.model_to_meta(model))

    def send(self, val=None, incr=False, args=None, step=0, oids=None,
             total=None, resume_url=None, finished=False):
        """
        Send a status update.

        All arguments are optional; no message will be sent if ``pct`` and
        ``args`` are absent.

        Most arguments, when using their default of ``None`` or similar, will
        not be included in the message--meaning all arguments are as
        non-destructive as possible. This means you can set, say, the
        ``resume_url`` once and never have to worry about it again. Of course,
        it's always safer to send all common arguments with each message, as
        clients may not be around for every message.

        :param val: An absolute or incremental number of units completed. If
            you have not specified ``total`` now or previously, an increment
            will silently fail.
        :param incr: Act as an incremental count? If ``True``, ``pct`` and any
            ``args`` values will be interpreted as changes relative to the
            current value (or zero if they are missing). Clients who miss
            messages will have invalid values; it is advisable to periodically
            send an absolute value to mitigate this issue.
        :param args: A mapping of template context used to render status
            body text on the client.
        :type args: dict
        :param step: Current step of an operation. Only necessary when the step
            has changed.
        :param total: Update the total amount of units 
        :type step: int, 0-indexed
        :param oids: Optionally provide a list of OIDs for this update. If
            ``None``, all associated with this Messenger will be updated. May
            also supply model instances like on init.
        :param resume_url: A link ``src`` value for where the user may proceed
            to view the details of the operation or continue along in the
            process.
        :param finished: Is the Operation finished? Pass ``True`` to set the
            finish time to now; otherwise, say when.
        :type finished: bool or datetime
        :returns bool: Whether or not the message was sent successfully.
        """
        keyed_data = {}
        data = dict(
            incr = incr,
            step = step,
        )

        if not val and not args and not total:
            return

        if not oids:
            oids = self.active_operation and [self.active_operation] or \
                   self.opset.operation_ids
        elif not isinstance(oids, (tuple, list, set)):
            oids = [oids]

        if val:
            data['val'] = val
        if total:
            data['total'] = total
        if args and isinstance(args, dict):
            data['args'] = args
        if finished:
            if finished == True:
                finished = datetime.now()
            data['finished_on'] = finished.strftime('%Y/%m/%d at %I:%M%p')
        if resume_url:
                data['resume_url'] = resume_url

        for oid in oids:
            if not isinstance(oid, basestring):
                oid = self.model_to_oid(oid)
            keyed_data[oid] = data

        try:
            self.opset.send_message(keyed_data)
            return True
        except ExpiredClientError, e:
            self.opset = e.opset
            self.clean()
            return False
        finally:
            if finished:
                for oid in oids:
                    self.finish(oid, resume_url, finished)

    def clean(self):
        """
        Remove deleted operations from our opset.
        """
        if not self.opset.key().name():
            ops = Operation.get_by_key_name(self.opset.operation_ids)
            stuff = zip(ops, self.opset.operation_ids)
            for checked, existing in stuff:
                if not checked:
                    self.opset.operation_ids.remove(existing)
            self.opset.put()

    def finish(self, oid=None, resume_url=None, when=None):
        """
        Finish a :class:`Operation`.

        :param oid: :class:`Operation` or :class:`Model` instance or string.
        :param resume_url: Set the ``resume_url`` field.
        :returns: ``None`` if Operation deleted; updated Operation otherwise.
        """
        when = when or datetime.now()
        oid = oid or self.active_operation
        op = None
        if isinstance(oid, Operation):
            op = oid
        elif not isinstance(oid, basestring):
            oid = self.model_to_oid(oid)
        if op is None:
            op = Operation.get_by_key_name(oid)
        if op:
            op.finished_on = datetime.now()
            if resume_url:
                op.resume_url = resume_url
                op.put()
                return op
            else:
                op.delete()
                return None
        return op


class BatchStatusHandler(BatchBaseHandler):
    """
    An alternate Batch Handler that provides automated status updates.
    """
    #: Probability of sending an absolute (full) status update vs. incremental
    full_update_probability = 0.5
    sent_total = False
    #: Used when calling batch_done(); set it to persist the Operation record.
    resume_url = None

    def __init__(self, *args, **kwargs):
        super(BatchStatusHandler, self).__init__(*args, **kwargs)
        self.messenger = Messenger(self.batch, domain=self.batch.domain)

    def unit_done(self, unit, chunk, success):
        """
        Push progress update to client.
        """
        def full_update():
            prog = self.batch.progress()
            incr = False
            val = prog['num_done_or_error']
            total = prog['num_total']
            args = {
                'done': prog['num_done'],
                'error': prog['num_error'],
                'skipped': prog['num_skipped'],
            }
            return (incr, val, args, total)

        incr = True
        val = 1
        total = None
        args = { 'incr': True }
        if success:
            args = { 'done': 1 }
        else:
            args = { 'error': 1 }
        # 25% chance to send a full update
        rand = random.uniform(0, 1)
        if rand <= self.full_update_probability or not self.sent_total:
            incr, val, args, total = full_update()
            self.sent_total = True
        result = self.messenger.send(oids=self.batch, incr=incr, val=val,
                                     args=args, total=total)
        if result == False:
            # We switched channels; send a full update just to be safe
            if incr == True:
                incr, val, args, total = full_update()
            result = self.messenger.send(oids=self.batch, incr=incr, val=val,
                                         args=args, total=total)

    def batch_done(self):
        """
        Clear operation, barring resume_url.
        """
        self.messenger.finish(self.batch, self.resume_url)


class UnitsStatusHandler(UnitsBaseHandler):
    """
    A mixable Units Handler that provides automated status updates.
    """
    #: Probability of sending an absolute (full) status update vs. incremental
    full_update_probability = 0.25
    #: Used when calling group_done(); set it to persist the Operation record.
    resume_url = None

    sent_total = False

    def full_update(self):
        prog = self.meta.progress()
        incr = False
        val = prog.num_done_or_error
        args = {
            'done': prog.num_done,
            'error': prog.num_error,
            'skipped': prog.num_skipped,
        }
        total = prog.num_total
        return (incr, val, args, total)

    def unit_done(self, unit, success, retrying):
        """
        Push progress update to client.
        """
        # % chance to send any update
        rand = random.uniform(0, 1)
        if rand < 0.5:
            return

        incr = True
        val = 1
        total = None

        if success:
            args = { 'done': 1 }
        elif not retrying:
            args = { 'error': 1 }
        else:
            return # Unit was put back into queue

        messenger = Messenger(self.meta, domain=self.meta.domain)

        # % chance to send a full update
        rand = random.uniform(0, 1)
        if rand < self.full_update_probability or not self.sent_total:
            incr, val, args, total = self.full_update()
            self.sent_total = True
        result = messenger.send(oids=self.meta, incr=incr, val=val,
                                args=args, total=total)
        if result == False:
            # We switched channels; send a full update just to be safe
            if incr == True:
                incr, val, args, total = self.full_update()
            result = messenger.send(oids=self.meta, incr=incr, val=val,
                                         args=args, total=total)

    def group_done(self):
        """
        Clear operation, barring resume_url.
        """
        incr, val, args, total = self.full_update()
        messenger = Messenger(self.meta, domain=self.meta.domain)
        messenger.send(oids=self.meta, incr=incr, val=val, args=args,
                       total=total, finished=True, resume_url=self.resume_url)

