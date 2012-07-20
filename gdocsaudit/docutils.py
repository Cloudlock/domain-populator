import gdata
import gdata.docs.data
from rfc3339 import rfc3339
import random
import logging
import os
import md5
import cPickle as pickle
from gdocsaudit import tools
from gdata.client import RequestError
from gdata.client import Unauthorized
from gdata.docs.client import DOCLIST_FEED_URI
from gdata.docs.data import DATA_KIND_SCHEME
from google.appengine.api import memcache
from datetime import datetime
import urllib
import urlparse

class ACL(list):
    """
    Wrapper around ACL entries to allow easier management / searching
    """
    acl = None

    def __init__(self, acl):
        list.__init__(self, acl)    

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
        items = kwargs.items()
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

def mk_acl_entry(scope_type, role, scope_value=None):
    """
    Simple utility function for making a :class:`gdata.docs.data.Acl` object.

    :param scope_type: The type of scope to create; 'user', 'group', 'domain'
        or 'default'.
    :param scope_value: The scope value; an email address or domain. Blank for
        ``default`` scope.
    :param role: Choices are 'reader', 'writer' and 'owner'.
    """
    scope = gdata.acl.data.AclScope(type=scope_type)
    if scope_type != "default":
        scope.value = scope_value
    role = gdata.acl.data.AclRole(value=role)
    return gdata.docs.data.Acl(scope=scope, role=role)

def _add_query_param(url, query_param):
    """
    Safely adds a query parameter to a URL

    :param url: URL string to which to add the query parameter
    :param query_param: query parameter string of the form "key=value" to be added to the URL
    """
    parsed_url = list(urlparse.urlparse(url))
    if parsed_url[4]: # query parameters
        parsed_url[4] += "&"
    parsed_url[4] += query_param
    return urlparse.urlunparse(parsed_url)

def _get_client_and_doc(auth, domain, *args):
    """
    Private helper function for getting an authenticated client and
    DocsEntry object(s).

    :param auth: The authentication user
    :param domain: The authentication domain
    :param *args: a list of documents or resource IDs to turn into
        :class:`gdata.docs.data.DocsEntry`
    :returns: A v3 API client and as many DocsEntry objects as you pass
    """
    client = tools.get_gapps_client('@'.join((auth, domain)), domain, svc='docsclient')
    docs = []
    for doc_id in args:
        if not isinstance(doc_id, gdata.docs.data.DocsEntry):
            doc = get_doc(doc_id, client=client)
        else:
            doc = doc_id
        docs.append(doc)
    if args:
        return [client] + docs
    else:
        return client

def _hash_doc(domain, doc):
    """
    Creates a simple hash of a document for use as a cache key.

    :param domain: The domain the document belongs to
    :param doc: The document's resource ID or ``DocsEntry`` object
    """
    try:
        return md5(':'.join((domain, doc))).hexdigest()
    except TypeError:
        return md5(':'.join((domain, doc.resource_id.text))).hexdigest()



def move_doc(owner, domain, doc_id, folder_id=None):
    """
    Move a document to a folder, optionally creating it if it doesn't exist.

    :param owner: The authenticated user to make the request as
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document.
    :param folder_id: The id (such as `folder:asdfas2423`) or DocsEntry object
        for the folder. If `folder_id` is `None`, the document is moved to the
        root folder.
    """
    client, doc = _get_client_and_doc(owner, domain, doc_id)
    if folder_id is None:
        return client.Move(doc, keep_in_folders=True)
    else:
        folder = get_or_create_doc(owner, domain, folder_id)
        return client.Move(doc, folder, keep_in_folders=True)



def create_empty_doc(owner, domain, title, batch_id,
                     doctype=gdata.docs.data.SPREADSHEET_LABEL, retry=True):
    """
    Create and upload a new empty document of type `doctype`.

    XXX: DOCUMENT_LABEL as a doctype does not work for unknown reasons!

    :param owner: The owner of this document; also used for authentication
    :param domain: The domain of the new document
    :param title: The title of the document
    :param doctype: a suitable document type as found in :mod:`gdata.docs.data`.
        As of this writing, one of: `DOCUMENT_LABEL`, `SPREADSHEET_LABEL` or
        `PRESENTATION_LABEL`.
    :returns: A :class:`gdata.docs.data.DocsEntry` object or None if it failed.
    """
    client = _get_client_and_doc(owner, domain)
    new_doc = None

    try:
        new_doc = client.Create(doctype, title)
    except RequestError, e:
        if e.status == 400 and retry:
            # Retry once because this can randomly fail
            return create_empty_doc(owner, domain, title, batch_id, doctype, retry=False)
        else:
            return None
    except Unauthorized:
        #TODO mark user as suspended so that later batches will run faster
        logging.warning("User is suspended")
        return None


    folder_id = memcache.get('folder_id:%s' % batch_id)
    folder_limit = memcache.get('folder_limit:%s' % batch_id)
    if new_doc is not None:
        if folder_id is not None:
            logging.info('folder_id: %s' % folder_id)
            if folder_limit > 0:
                folder = get_doc(folder_id, client=client)
                memcache.set('folder_limit:%s' % batch_id, folder_limit - 1)
                return client.Move(new_doc, folder, keep_in_folders=True)

        logging.info('Document "%s" created for user "%s" on domain "%s".',
                     new_doc.title.text, owner, domain)
        return new_doc
    else:
        return None

def create_folder(owner, domain, title, batch_id,
                     doctype=gdata.docs.data.FOLDER_LABEL, retry=True):
    """
    Create and upload a new empty document of type `doctype`.

    XXX: DOCUMENT_LABEL as a doctype does not work for unknown reasons!

    :param owner: The owner of this document; also used for authentication
    :param domain: The domain of the new document
    :param title: The title of the document
    :param doctype: a suitable document type as found in :mod:`gdata.docs.data`.
        As of this writing, one of: `DOCUMENT_LABEL`, `SPREADSHEET_LABEL` or
        `PRESENTATION_LABEL`.
    :returns: A :class:`gdata.docs.data.DocsEntry` object or None if it failed.
    """
    client = _get_client_and_doc(owner, domain)
    new_doc = None

    try:
        new_doc = client.Create(doctype, title)
    except RequestError, e:
        if e.status == 400 and retry:
            # Retry once because this can randomly fail
            return create_folder(owner, domain, title, batch_id, doctype, retry=False)
        else:
            return None
    except Unauthorized:
        #TODO mark user as suspended so that later batches will run faster
        logging.warning("User is suspended")
        return None

    if new_doc:
        logging.info('Document "%s" created for user "%s" on domain "%s".',
                     new_doc.title.text, owner, domain)
        return new_doc
    else:
        return None

def create_pdf(owner, domain, title, batch_id, retry=True):
    client = _get_client_and_doc(owner, domain)
    new_doc = None
    try:
        try:
            f = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'testpdf.pdf'))
            ms = gdata.data.MediaSource(file_handle=f, content_type='application/pdf', content_length=os.path.getsize(f.name))
            new_doc = client.Upload(ms, title, folder_or_uri=gdata.docs.client.DOCLIST_FEED_URI + '?convert=false')
            logging.info('Document now accessible online at: %s', new_doc.GetAlternateLink().href)
        except RequestError, e:
            if e.status == 400 and retry:
                #TODO this apparently works for free apps domains
                return create_pdf(owner, domain, title, batch_id, retry=False)
        except Unauthorized:
            #TODO mark user as suspended so that later batches will run faster
            logging.warning("User is suspended")
            return None

    except RequestError, e:
        return None

    folder_id = memcache.get('folder_id:%s' % batch_id)
    folder_limit = memcache.get('folder_limit:%s' % batch_id)
    if new_doc:
        if folder_id is not None and folder_limit > 0:
            folder = get_doc(folder_id, client=client)
            memcache.set('folder_limit:%s' % batch_id, folder_limit - 1)
            return client.Move(new_doc, folder, keep_in_folders=True)

        logging.info('Document "%s" created for user "%s" on domain "%s".',
                     new_doc.title.text, owner, domain)
        return new_doc
    else:
        return None

def delete_doc(owner, domain, doc_id, force=False, trash=True):
    """
    Delete a document owned by `owner` with id `doc_id` in domain `domain`.

    :param owner: The current owner (who we'll authenticate as)
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document.
    :param force: Force the deletion regardless of other clients
    :param trash: Move the document to the trash; do not fully delete it
    """
    client = _get_client_and_doc(owner, domain)
    if not isinstance(doc_id, gdata.docs.data.DocsEntry):
        doc = get_doc(doc_id, client=client)
    else:
        doc = doc_id
    try:
        if trash:
            client.Delete(doc, force=force)
        else:
            client.Delete(doc.GetEditLink().href + '?delete=true', force=True)

        logging.info('Document "%s" deleted from domain "%s".', doc.title.text,
                     domain)
    except RequestError, e:
        if e.status == 412: #You're probably trying to trash a trashed doc
            pass
    except Unauthorized:
        #TODO mark user as suspended so that later batches will run faster
        logging.warning("User is suspended")
        return None
    #uncache_doc(domain, doc)
    return True

def get_doc(resource_id, auth=None, domain=None, client=None, ttl=900, debug=False):
    """
    Retrieve document with ``resource_id`` from cache or cache and return it.
    Accepts either a qualified client or an ``(auth, domain)`` pair.

    :param auth: The authentication user (optional; must be used with
        ``domain``)
    :param domain: The authentication domain (optional; must be used with
        ``auth``)
    :param client: Qualified client (:class:`gapps.docs.client.DocsClient`);
        used instead of auth and domain.
    :param doc: The document resource ID to retrieve
    :param ttl: The length of time the cached object should live in *seconds*
    :param debug: If ``True``, returns a tuple of the form ``(doc, from_cache)``
        where the latter is a boolean indicating if the document is from
        memcache or not.
    """
    if (not auth and not domain) and not isinstance(client, gdata.docs.client.DocsClient):
        raise ValueError('You must supply an auth/client combo or DocsClient!')
    from_cache = True

    if not client:
        client = _get_client_and_doc(auth, domain)
    #key = _hash_doc(client.domain, resource_id)
    #cached = memcache.get(key)
    #if cached is None:
    #    from_cache = False
    doc = client.GetDoc(resource_id)
    p = pickle.dumps(doc)
    #    memcache.add(key, p, ttl)
    cached = p
    obj = pickle.loads(cached)
    if debug:
        return (obj, from_cache)
    return obj

def get_docs(owner, domain, categories=None, filetype=None, showfolders=None,
             count=100, follow=True, contents_of=None, category_fix=True,
             **kwargs):
    """
    Retrieve a list of documents based on search criteria.

    :param owner: The user to authenticate as
    :param domain: The domain of the documents we're querying
    :param category: Categories types to filter by. Currently available:

        * document
        * drawing
        * folder
        * pdf
        * presentation
        * spreadsheet
        * form
        * starred
        * trashed
        * hidden
        * viewed
        * mine
        * private
        * shared-with-domain

    :type category: iterable
    :param category_fix: Due to a "feature" of Google's API, **title searches
        may need to be done manually when categories are specified!** This
        appears to have been fixed as of this update, but this parameter exists
        in case you find cases where it doesn't.
    :param filetype: A specifc filetype to find, i.e. `application/msword`.
        Schemas will be added for you.
    :param showfolders: Include folders in the results?
    :param count: Maximum number of documents
    :param \*\*kwargs: Arguments that will be converted to a querystring to be
        added to the request. A reference of parameters is available at:
        http://code.google.com/apis/documents/docs/3.0/reference.html#Parameters
        Booleans are an accepted type for true/false values. Dashes in parameter
        names should be converted to underscores.
    :param follow: Continue following the next URL to get more results or stop?
    :param contents_of: Retrieve content of a given folder (resource ID)
    """
    # basics
    title = kwargs.get('title')
    title_exact = kwargs.get('title_exact')
    KIND = '{' + DATA_KIND_SCHEME + '}'
    path = DOCLIST_FEED_URI
    client = _get_client_and_doc(owner, domain)
    # update query params
    kwargs['max-results'] = count
    if showfolders is not None:
        kwargs['showfolders'] = showfolders

    for k, v in kwargs.items():
        if '_' in k:
            del kwargs[k]
            k = k.replace('_', '-') 
        # allow boolean query values
        if type(v) == bool:
            kwargs[k] = str(v).lower()
        # allow datetime/timestamp
        elif type(v) == datetime:
            kwargs[k] = rfc3339(v)
        else:
            kwargs[k] = str(v)
    # XXX: Providing title means categories are ignored!
    if 'title' in kwargs and ((category_fix and categories is not None) or
                              contents_of is not None):
        title = kwargs['title']
        del kwargs['title']
        if 'title-exact' in kwargs:
            title_exact = kwargs['title-exact']
            del kwargs['title-exact']
    # handle categories, etc.
    if contents_of is not None:
        path += urllib.quote(contents_of) + '/contents/'
        kwargs['showfolders'] = 'true'
    if categories is not None:
        path += '-/' + '/'.join(categories)
    if filetype is not None:
        ft = '/' + urllib.quote(KIND + filetype)
        path += ft
    # build querystring
    query_string = '&'.join(['='.join((k,urllib.quote(str(v)))) for (k,v) in kwargs.items()])
    final = '?'.join((path, query_string))
    logging.info('Retrieving documents: %s', final)
    next_uri = final
    while True:
        docs = client.GetDocList(next_uri)
        for entry in docs.entry:
            if (not title or
                (title_exact and entry.title.text.lower() == title.lower()) or
                (not title_exact and title.lower() in entry.title.text.lower())
            ):
                yield entry
        next_uri = docs.find_next_link()
        if not next_uri or not follow:
            break

def share_domain(owner, domain, doc_id):
    """
    Modify the ACL for a document by giving `user` the specified `role`.

    :param owner: The authenticated user to make the request as
    :param user: The user who's gaining an ACL entry
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document
    :param role: Can be "reader", "writer", or None -- if None, ACL entry will
        be deleted
    :returns: The modified entry
    """
    rolecount = random.randint(0,2)
    if rolecount == 0:
        role = 'reader'
    else:
        role = 'writer'

    #TODO figure out whether to do reader or writer

    client, doc = _get_client_and_doc(owner, domain,doc_id)
    scope = gdata.acl.data.AclScope(value=domain, type='domain')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, doc.GetAclFeedLink().href)

def share_public(owner, domain, doc_id):
    """
    Modify the ACL for a document by giving `user` the specified `role`.

    :param owner: The authenticated user to make the request as
    :param user: The user who's gaining an ACL entry
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document
    :param role: Can be "reader", "writer", or None -- if None, ACL entry will
        be deleted
    :returns: The modified entry
    """

    role = 'reader'
    
    client,doc = _get_client_and_doc(owner, domain,doc_id)

    scope = gdata.acl.data.AclScope(value=None, type='default')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, doc.GetAclFeedLink().href)

def share_user(owner, domain, doc_id, user):
    """
    Modify the ACL for a document by giving `user` the specified `role`.

    :param owner: The authenticated user to make the request as
    :param user: The user who's gaining an ACL entry
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document
    :param role: Can be "reader", "writer", or None -- if None, ACL entry will
        be deleted
    :returns: The modified entry
    """
    rolecount = random.randint(0,2)
    if rolecount == 0:
        role = 'reader'
    else:
        role = 'writer'


    client, doc = _get_client_and_doc(owner, domain, doc_id)

    scope = gdata.acl.data.AclScope(value=user, type='user')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, doc.GetAclFeedLink().href)


def get_users_docs(owner, domain, nextLink=None):
    """
    Get a users list of docs

    :param owner: The authenticated user to make the request as
    :param user: The user who's gaining an ACL entry
    :param domain: The domain of the document we're modifying
    :param doc_id: The id (such as `document:asdfas2423`) or DocsEntry object
        for the document
    :param role: Can be "reader", "writer", or None -- if None, ACL entry will
        be deleted
    :returns: The modified entry
    """

    client = _get_client_and_doc(owner, domain)

    if nextLink:
        feed = client.GetDocList(uri=nextLink)
    else:
        feed = client.GetDocList(uri='/feeds/default/private/full/-/mine?showfolders=true')
    nextLink = feed.GetNextLink()

    return (feed, nextLink)

def get_doc_acl(owner, domain, docish):
    """
    A thin wrapper around client.GetAclPermissions().

    :param owner: The authenticated user to make the request as
    :param domain: The domain of the document we're modifying
    :param docish: The resource ID (such as `folder%3Aasdfas2423`) or DocsEntry
        object.
    """
    
    def fix_role(entry):
        role = entry.role.value
        if not role or role.lower() == 'none':
            k = entry.FindChildren('withKey')
            if len(k) > 0:
                role = k[0].FindChildren('role')[0].value
            entry.role.value = role
        return entry

    client, doc = _get_client_and_doc(owner, domain, docish)
    entries = client.GetAclPermissions(doc.resource_id.text).entry
    return ACL([fix_role(e) for e in entries])

def mod_acl(owner, domain, doc_id, scope_value, scope_type='user',
            role='reader', force_post=False, send_email=False, retain_permissions=False):
    """
    Modify the ACL for a document, setting the `role` for the given
    `scope_type` and `value`. Unlike mod_user_acl, this function allows you
    to specify a scope type other than user; the full list of possible
    scope types is:

      * `user` - value is user@domain
      * `group` - value is groupname@domain
      * `domain` - shared with everyone in the domain; value is the domain,
        e.g. example.com
      * `default` - shared with the public internet; no value
        (parameter is ignored, you should pass None)

    The new "retain_permissions" arg will only update the acl of an existing document if you wish to increase
    permissions for that user on the document. 
    """

    def update_acl(existing):
        if existing:
            existing.role.value = role
            existing.scope.value = scope_value
            # XXX: w/o force, might raise
            # RequestError(412, Resource does not support ETags)
            return client.Update(existing, force=True)
        else:
            return None

    if role is None:
        return delete_acl_entry_scoped(owner, scope_type, scope_value,
                                       domain, doc_id)


    logging.info("owner %s domain %s doc_id %s" % (owner, domain, doc_id))
    client, doc = _get_client_and_doc(owner, domain, doc_id)

    acl_feed = get_doc_acl(owner, domain, doc)

    findargs = { 'scope_type': scope_type }
    # We always want to modify the owner
    if scope_type != 'default' and role != 'owner':
        findargs['scope_value'] = scope_value
    elif role == 'owner':
        findargs['role'] = 'owner'
    existing_entries = acl_feed.find(**findargs)

    existing = None
    if existing_entries:
        if len(existing_entries) > 1:
            logging.error(("More than one ACL entry has scope type=%s, "
                           "value=%s. This is an unexpected condition on "
                           "the document: %s") % (scope_type,
                                                  scope_value,
                                                  str(doc)))
        existing = existing_entries[0]
        
    if force_post or not existing_entries:
        acl_entry = mk_acl_entry(scope_type=scope_type, role=role,
                                 scope_value=scope_value)
        qp = "send-notification-emails=%s" % str(send_email).lower()
        new_href = _add_query_param(url=doc.GetAclFeedLink().href, query_param=qp)
        return client.Post(acl_entry, new_href)
    elif retain_permissions and existing:
        #This piece of code allows us to only increase a user's privileges and never decrease. 
        role_priority_map = {'reader':0,
                             'writer':1,
                             'owner': 2}
        if role_priority_map[existing.role.value] >= role_priority_map[role]:
            return None
    return update_acl(existing)

