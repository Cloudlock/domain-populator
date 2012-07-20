from django.core.serializers.json import simplejson as json
from django.http import Http404, HttpResponse

from units.models import OperationMeta


def xhr_totals(request):
    """
    Retrieve the totals for an operation.
    """
    totals = {}
    get_oid = request.GET.get('oid')
    _, oid = get_oid.split(':')

    op = OperationMeta.get_by_id(int(oid))
    if not op:
        raise Http404()

    prog = op.progress()
    totals = {
        'val': prog.num_done_or_error,
        'total': prog.num_total,
        'oid': get_oid
    }
    return HttpResponse(json.dumps(totals))

