from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import simplejson as json
from grid.paginator import CursorPaginator as Paginator


def get_sorts(request, sort_map):
    """
    Given a DataTable-initiated request, find its sorts.

    :param request: Django request object
    :param sort_map: Dictionary of "index -> field_name". The index is obtained
        as ``iSortCol_<id>``.
    """
    sorts = []
    keys = filter(lambda k: k.startswith('iSortCol_'), request.REQUEST.keys())
    for key in keys:
        i = int(key[-1])
        field = sort_map[int(request.REQUEST.get(key))]
        order = request.REQUEST.get('sSortDir_%d' % i, 'desc')
        field = field if order == 'asc' else '-'+field
        sorts.append(field)
    return sorts


def get_page(request, query, json_tpl, render_ctx=None, resp_ctx=None):
    """
    Render rows of JSON as response to DataTable queries.

    :param query: A :class:`Query` instance to get a page of
    :param json_tpl: Name of the template which will render the page objects as
        JSON rows
    :param render_ctx: If a dictionary, will act as the default context for the
        template render. If a callable, should take ``obj`` (Query row) as a
        parameter and return a dictionary which will be used for the render.
    :type render_ctx: dict or callable
    :param resp_ctx: Add to the response dictionary JSON dump.
    :type resp_ctx: dict
    """
    resp_ctx = resp_ctx or {}
    echo = request.GET.get('sEcho', 0)
    size = int(request.GET.get('iDisplayLength', 10))
    start = int(request.GET.get('iDisplayStart', 0))

    pager = Paginator(query, size, prefetch=True)
    page_num = (start / size) + 1
    page = pager.page(page_num)
    obj_list = page.object_list

    json_rows = []
    for obj in obj_list:
        if callable(render_ctx):
            context = render_ctx(obj)
        else:
            context = render_ctx or {}
        context.update({'obj': obj,
                   'domain': request.domain_setup.domain,
                   'ds': request.domain_setup })
        rendered_row = render_to_string(
            json_tpl,
            context
        ).replace('\n', '').strip()
        json_rows.append(json.loads(rendered_row))

    response = {
        'sEcho':int(echo),
        'iTotalRecords': pager.count,
        'iTotalDisplayRecords': pager.count,
        'aaData': json_rows,
    }
    response.update(resp_ctx)
    json_text = json.dumps(response)
    return HttpResponse(json_text, mimetype='application/json')


def tag_ctx_factory(obj):
    """
    Split a :class:`LogEntry` tags on ":" and return a dictionary.

    Only splits on the first colon!
    """
    return dict([s.split(':', 1) for s in obj.tags])

