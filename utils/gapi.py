from atom.data import Title
from django.utils import simplejson
from gapps.collab import annotate_collab_entry
from gdata.acl.data import AclEntry, AclRole, AclScope


class exposures(object):
    """
    Constants for defining an ACL entry's exposure surface.
    """
    #: Not an exposure (e.g. owner)
    NONE = 0
    #: Exposes entity internally (to individual/group)
    INTERNAL = 1
    #: Exposes entity internally (to entire domain)
    INTERNAL_ALL = 2
    #: Exposes entity externally (to individual/group)
    EXTERNAL = 3
    #: Exposes entity publicly
    PUBLIC = 4


class ACL(list):
    """
    Wrapper around ACL entries to allow easier management / searching

    :param acl: A bonfied :class:`gdata.acl.data.AclEntry` or equivalent, OR
    :param serialized_acl: A pre-serialized version of an ACL, as obtained via
        :meth:`serialize`.
    """
    acl = None

    def __init__(self, acl=None, serialized_acl=None):
        acl = acl or []
        if serialized_acl:
            assert acl == [], ('Cannot initialize a new ACL object '
                               'using both an existing acl *and* a '
                               'serialized_acl.')
            acl = []

        super(ACL, self).__init__(acl)

        if serialized_acl:
            self.deserialize(serialized_acl)

    @classmethod
    def from_aclentry_list(cls, entrylist):
        """
        Obtain an instance from, e.g., a feed's ``entry`` attribute.
        """
        return cls([fix_role_in_acl_entry(e) for e in entrylist])

    @staticmethod
    def acl_entry_to_dict(aclentry):
        """
        Convert an ACL entry to a dictionary.

        Keys used: ``role``, ``type``, ``value``
        """
        result = dict(
            role=aclentry.role.value or '',
            type=aclentry.scope.type or '',
            value=aclentry.scope.value or '')
        if hasattr(aclentry, 'title') and aclentry.title is not None:
            result['title'] = aclentry.title.text or ''
        return result

    @staticmethod
    def dict_to_acl_entry(d):
        """
        Reverse of :meth:`acl_entry_to_dict`.
        """
        result = AclEntry()
        result.title = Title(title=d.get('title', ''))
        result.role = AclRole(value=d.get('role', ''))
        result.scope = AclScope(type=d.get('type', ''),
                                value=d.get('value', ''))
        return result

    def __getpair(self, key):
        """
        Get the appropriate (field, attribute) pair for the given find() kwarg.
        """
        attr = 'value'
        if key == 'title':
            attr = 'text'
        elif key == 'scope_type':
            key = 'scope'
            attr = 'type'
        elif key == 'scope_value':
            key = 'scope'

        return key, attr

    def find(self, **kwargs):
        """
        Find all ACL entries that match the given keyword arguments.

        If the value of a keyword argument is "falsey" (None, False, '', etc.)
        it will be skipped.

        Available keywords are:

            * title
            * role
            * scope_value
            * scope_type

        :returns: list of matching ACL entries
        """
        hits = []
        if not kwargs:
            return self

        items = filter(lambda i: i[1], kwargs.items())

        for entry in self:
            good = 0
            for key, val in items:
                key, attr = self.__getpair(key)
                try:
                    prop = getattr(entry, key)
                    check = getattr(prop, attr)
                except AttributeError:
                    continue
                if ((val is not None and check is not None 
                     and check.lower() != val.lower())
                    or (val != check)):
                    continue
                good += 1
            if good == len(items):
                hits.append(entry)

        return hits

    def serialize(self):
        """
        Convert from ACLS to raw format

        :returns: JSON-encoded string
        """
        return simplejson.dumps([ACL.acl_entry_to_dict(e) for e in self])

    def deserialize(self, serialized_acl):
        """
        Given a JSON ACL, add the entries in that ACL to this instance.

        :param serialized_acl: the serialized string
        """
        ds = simplejson.loads(serialized_acl)
        self.extend([ACL.dict_to_acl_entry(d) for d in ds])

    def annotate(self, domains):
        """
        Get annotated ``dict``s for this ACL.

        Each entry will be represented as a dictionary with the following keys:

        * ``type`` -> scope type
        * ``value`` -> scope value
        * ``role`` -> scope's role
        * ``is_owner`` -> Boolean indicating ownership
        * ``can_edit`` -> Boolean indicating edit ability
        * ``exposure`` -> one of: ``exposures.PUBLIC``, ``exposures.INTERNAL``,
            ``exposures.EXTERNAL``

        :param domains: Domain(s) used to compute exposure. The first value 
        :type domains: string or list/tuple/etc.
        """
        if isinstance(domains, basestring):
            domains = (domains,)

        annotated = []
        for entry in self:
            # Basic conversion
            d = ACL.acl_entry_to_dict(entry)
            # Annotate
            annotate_collab_entry(d, domains)
            # Booleans
            d['is_owner'] = d['role'] == 'owner'
            d['can_edit'] = d['role'] in ('owner', 'writer')
            # Exposure
            d['exposure'] = ACL.get_exposure(d, domains)
            annotated.append(d)

        return sorted(annotated, key=lambda e: (e['role'], e['value']))

    @staticmethod
    def get_exposure(d, domains):
        """
        Determine the exposure surface of an ACL entry (as ``dict``).

        :param d: A ``dict`` form of an ACL entry
        :param domains: List of domains to check exposures against

        :returns: A constant-attr found in :class:`exposures`
        """
        try:
            domain = d['value'].split('@')[1]
        except IndexError:
            domain = None
        if d['type'] == 'default':
            return exposures.PUBLIC
        elif d['value'] == 'everyone' or d['type'] == 'domain':
            return exposures.INTERNAL_ALL
        elif domain in domains:
            return exposures.INTERNAL
        else:
            return exposures.EXTERNAL


def iterfeed(fetch, **kwarg):
    """
    Iterate through feed entries as seeded with ``fetch(start)``.

    This function follows the "next_link" property present on most Google
    resource feeds. It will yield individual entries until all uris have
    been exhausted.

    :param fetch: Method/function to call with ``start``
    :param kwarg: A named argument (and optional initial value) used to pass
        along the next uri.
    """
    key = kwarg.keys()[0]

    while True:
        feed = fetch(**kwarg)
        for entry in feed.entry:
            yield entry
        kwarg[key] = feed.find_next_link()
        if not kwarg[key]:
            break


def cmp_acl_mod(a, b):
    """
    Comparison function (used in :func:`sorted`) to order ACL modifications.
    """
    # Always add first
    if a['role'] == 'add':
        return 1
    elif b['role'] == 'add':
        return -1
    # Modification before removal
    if a['role'] == 'mod' and b['role'] == 'rm':
        return 1
    elif b['role'] == 'mod' and a['role'] == 'rm':
        return -1
    return 0


def fix_role_in_acl_entry(entry):
    """
    Utility for fixing up "withKey" ACL entries.
    """
    try:
        role = entry.role.value
        assert role and role.lower() != 'none'
    except (AttributeError, AssertionError):
        k = entry.FindChildren('withKey')
        if len(k) > 0:
            role = k[0].FindChildren('role')[0]
            entry.role = role
    return entry

