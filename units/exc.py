class UnitsException(Exception):
    pass


class DelayUnit(UnitsException):
    """
    Delay a unit of work; optional custom delay.
    """
    def __init__(self, delay=0):
        self.delay = delay


class DelayOperation(UnitsException):
    """
    Delay an entire operation; optional custom delay.
    """
    def __init__(self, delay=0):
        self.delay = delay


class UnitError(UnitsException):
    """
    An exception occurred while handling a unit.
    """
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

    def __unicode__(self):
        full_msg = '\n'.join((self.msg, self.tb))
        return 'Unit %s Operation #%s: %s' % (self.unit,
                                              self.op.key().id(),
                                              full_msg)
    __str__ = __unicode__


class TooManyDelays(UnitsException):
    """
    Like the name says...
    """


class OperationActive(UnitsException):
    """
    An operation is still active; cannot complete request.
    """
