import logging
import random
import string

from django.core.serializers.json import simplejson as json
from django.http import Http404, HttpResponse

from gdata.client import RequestError
from gapps.decorators import requires_domain_oid_admin
from status import Messenger, BatchStatusHandler
from status.models import Operation, OperationSet
from shortcuts import render
import units
from units import handlers


class StatusTestBatchHandler(BatchStatusHandler):
    key = 'status-test'
    def build_chunks(self, cp=None):
        chunk = self.get_chunk_clone()
        chunk.units_pending = list(string.letters)
        chunk.put()
        yield chunk

    def do_unit(self, unit, chunk):
        count = 0
        for x in xrange(0, 10000000):
            count += 1
        return True


class StatusTestUnitsHandler(handlers.BaseHandler):
    delay_codes = [5]

    def prerun(self):
        logging.warn('Op prerun!')

    def iterunits(self):
        for letter in string.letters:
            yield letter

    def op_done(self):
        logging.warning(list(self.meta.queue('skipped').items()))
        logging.warning(list(self.meta.queue('error').items()))

    def group_done(self):
        logging.warning('Group done!')

    def do_unit(self, unit):
        count = 0
        for x in xrange(0, 500000):
            count += 1
        if unit == 'q':
            e = RequestError()
            e.status = 5
            e.body = 'foo!'
            raise e
        if unit == 'f':
            raise ValueError()
        return True


def token(request, domain, clear=False):
    """
    Get or create a token for a set of operations
    """
    data = json.loads(request.POST.get('data', {}))
    if 'operation_ids' not in data and 'domain' not in data:
        raise Http404
    if data.get('domain', False):
        opset = OperationSet.get_or_create(domain=domain)
    else:
        opset = OperationSet.get_or_create(operation_ids=data['operation_ids'])
    if clear:
        opset.current_token = None
        opset.token_stamp = None

    return HttpResponse(opset.token)


@requires_domain_oid_admin
def test(request, domain):
    if Operation.all().filter('domain', domain).count() == 0 and request.GET.get('seed'):
        Operation(key_name='domain1', domain=domain,
                  label='Something important').put()
        Operation(key_name='domain2', domain=domain,
                  label='Something cool').put()

    ops = dict(
        operation_id = 'test:0',
        operation_id2 = 'test:1',
        operation_id3 = 'test:2'
    )
    [s.delete() for s in OperationSet.all()]
    return render(request, 'status/test.html', ops)


@requires_domain_oid_admin
def test_send(request, domain):
    messenger = Messenger(namespace='test', ids=range(0,3))
    sub  = OperationSet.get_or_create('test:0')
    dos = OperationSet.get_or_create(domain=domain)
    dmess = Messenger(dos)
    step = request.GET.get('step', 0)

    pct = [random.randint(0, 100) for x in range(3)]
    test = { 'val': 30, 'incr': True, 'oids': 'test:0' }
    ops = {
        'test:1': { 'val': pct[1],
                    'args': { 'done': pct[1], 'total': 100 },
                    'incr': True },
        'test:2': { 'val': pct[2],
                    'step': step,
                    'args': { 'done': pct[2], 'total': 100 } },
    }
    sub.send_message(ops)
    messenger.send(**test)
    dmess.send(val=50, total=100, args={ 'done': 50, 'error': 0 },
               incr=True, finished=True)

    return HttpResponse(str(pct))


@requires_domain_oid_admin
def test_op(request, domain):
    if request.method == 'POST':
        op = units.operation(['status.views.StatusTestUnitsHandler', 'status.UnitsStatusHandler'])
        op.domain = domain
        op.put()
        op.start()
        return HttpResponse(op.key().id())
    raise Http404


def operations(request, domain):
    """
    Retrieve a list of Operations for a domain
    """
    query = Operation.all().filter('domain', domain)
    ops = json.dumps([{ 'label': o.label,
                        'id': o.key().name(),
                        'finished_on': (o.finished_on and
                            o.finished_on.strftime('%Y/%m/%d at %I:%M%p')
                            or None),
                        'resume_url': o.resume_url } for o in query])
    return HttpResponse(ops)


def missing(request, domain):
    """
    Attempt to retrieve information about an operation that is missing info on
    the client.
    """
    oid = request.GET.get('oid')
    op = Operation.get_by_key_name(oid)
    if op:
        ops = [{ 'label': op.label,
                 'id': op.key().name(),
                 'finished_on': (op.finished_on and
                    op.finished_on.strftime('%Y/%m/%d at %I:%M%p')
                    or None),
                 'missing': True,
                 'resume_url': op.resume_url }]
    else:
        ops = [{ 'id': oid, 'missing': True }]
    return HttpResponse(json.dumps(ops))


def finished(request, domain):
    """
    An operation finished; delete it or keep it around for resuming.
    """
    operation_id = request.POST.get('operation_id')
    force = request.POST.get('force')
    if not operation_id:
        raise Http404
    op = Operation.get_by_key_name(operation_id)
    if op and (not op.resume_url or force):
        op.delete()
    Messenger(domain=domain).clean()

    return HttpResponse('OK')

