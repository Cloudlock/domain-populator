import cgi
import urllib
import urlparse
from collections import defaultdict


def add_query_param(uri, key, value, replace=None):
    """
    Safely adds a query parameter to a URL

    :param uri: URI string to which to add the query parameter
    :param key: Parameter name
    :param value: Parameter value
    :param replace: If ``None``, add another value for ``key``. If ``True``,
        replace any existing values with ``value``. If ``False``, do not add
        additional values; retain existing.
    """
    if value is None:
        return uri

    query_twos = []
    parts = list(urlparse.urlsplit(uri))
    query = parts[3]
    query_dict = defaultdict(list, cgi.parse_qs(query))
    if replace is None or (replace == False and len(query_dict[key]) == 0):
        query_dict[key].append(value)
    elif replace == True:
        query_dict[key] = [value]
    for k, v in query_dict.items():
        for val in v:
            query_twos.append((k, val))
    parts[3] = urllib.urlencode(query_twos)
    return urlparse.urlunsplit(parts)

