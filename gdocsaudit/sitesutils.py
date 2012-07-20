from __future__ import absolute_import

import random
import logging
from gdocsaudit import tools
from utils.uri import add_query_param
from utils.gapi import iterfeed, ACL
import gdata.sites.data


def _get_client(auth, domain):
    """
    Helper function to get an authenticated sites client.

    :param auth: The authentication user
    :param domain: The authentication domain
    :returns: A gdata.sites.client.SitesClient API client
    """
    client = tools.get_gapps_client('@'.join((auth, domain)), domain,
                                    svc='sites')
    return client


def get_sites_feed(auth, domain, max_results=None, uri=None):
    """
    Retrieve the raw feed of sites associated with the given domain.

    :param auth: The user to authenticate as
    :param domain: The domain whose sites we're querying
    :param uri: URI to query, generally only used if you are paging through
      results (see max_results).
    :param max_results: An integer specifying the maximum number of results
      per response. (Use sitefeed.GetNextLink() to get the next page's URI.)
      Note that if your URI already includes a max_results parameter this
      parameter will have no effect.
    """
    client = _get_client(auth, domain)
    uri = uri or client.make_site_feed_uri()
    uri = add_query_param(uri, 'max-results', max_results, replace=False)
    feed = client.GetSiteFeed(uri=uri)
    return feed


def get_sites(auth, domain, max_results=None, deleted=None):
    """
    Generator yielding site entries which match the given critera.

    :param max_results: An integer specifying the maximum number of results
      per response.
    :param deleted: Include sites that are probably deleted? ``True`` will
        include *only* deleted sites where ``False`` will exclude deleted ones.
    """
    client = _get_client(auth, domain)
    uri = client.make_site_feed_uri()
    for site in iterfeed(client.get_site_feed, uri=uri):
        yield site


def create_site(auth, domain, site_title, site_description=None,
                site_theme=None):
    """
    Create a new Google Site in the given domain, owned by the provided user.

    :param auth: The user to authenticate as
    :param domain: The domain whose sites we're querying
    :param site_title: Title for the site (required)
    :param site_description: text description for the site (optional)
    :param site_theme: Visual theme for the site, e.g. 'slate' (optional)

    :returns: a SiteEntry object, view it at entry.GetAlternateLink().href
    """
    client = _get_client(auth, domain)
    entry = client.CreateSite(site_title,
                              description=site_description,
                              theme=site_theme)
    return entry


def get_site_entry_by_id(auth, domain, site_id):
    """
    Get a site entry object given an id.

    :param auth: The user to authenticate as
    :param domain: The domain whose sites we're querying
    :param site_id: id of the site we're looking for. This is an https
       uri, something like:
       https://sites.google.com/feeds/site/peepdex.com/sites-test-1
       ...and can be gotten by calling .get_id() on a SiteEntry object.
    """
    client = _get_client(auth, domain)
    site_entry = client.GetEntry(site_id,
                                 desired_class=gdata.sites.data.SiteEntry)
    return site_entry


def get_client_for_site(auth, domain, site_id_or_obj):
    """
    Get a site client with its current site set. You need this to query for
    content within a site.

    :param auth: The user to authenticate as
    :param domain: The domain whose sites we're querying
    :param site_id: id of the site we're looking for. This is an https

    :returns: a gdata.sites.client.SitesClient client with .site set.
    """
    if isinstance(site_id_or_obj, gdata.sites.data.SiteEntry):
        site = site_id_or_obj
    else:
        site = get_site_entry_by_id(auth, domain, site_id_or_obj)

    client = _get_client(auth, domain)
    client.site = site.site_name.text

    return client


def get_site_acl(auth, domain, site_id_or_obj):
    c = get_client_for_site(auth, domain, site_id_or_obj)
    entries = c.GetAclFeed().entry
    return ACL.from_aclentry_list(entries)

def share_user(owner, domain, site_id, user):
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
    rolecount = random.randint(0,3)
    if rolecount == 0:
        role = 'reader'
    elif rolecount == 1:
        role = 'writer'
    else:
        role = 'owner'


    client = get_client_for_site(owner, domain, site_id)

    scope = gdata.acl.data.AclScope(value=user, type='user')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, client.MakeAclFeedUri())


def share_domain(owner, domain, site_id):
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

    client = get_client_for_site(owner, domain, site_id)

    scope = gdata.acl.data.AclScope(value=domain, type='domain')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, client.MakeAclFeedUri())


def share_public(owner, domain, site_id):
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

    client = get_client_for_site(owner, domain, site_id)

    scope = gdata.acl.data.AclScope(value=None, type='default')
    role = gdata.acl.data.AclRole(value=role)
    acl_entry = gdata.docs.data.Acl(scope=scope, role=role)
    return client.Post(acl_entry, client.MakeAclFeedUri())
    

