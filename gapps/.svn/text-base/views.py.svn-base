# gapps.views

from decorators import requires_domain_oid_admin, requires_domain_oid, taskqueue_only
from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.conf import settings
from django.utils import simplejson
from django.utils.http import urlquote
from django.utils.encoding import smart_unicode

from google.appengine.api import users

from google.appengine.api import channel

import enqueue
import pickle
import models
from models import DomainSetup, BatchOperation, NumDocSetup, ShareSetup, DocTypeSetup, ServiceHelper
from forms import CreateDocsForm, InternalShareSettingsForm, ExternalUsersForm, ExternalShareSettingsForm, DocTypeSettingsForm, CreateUsersForm, NumDocSettingsForm
from gdata.client import RequestError
from gdata.apps.service import AppsForYourDomainException
from gdata.service import BadAuthentication
import gdata.apps.service
import gdata.apps.adminsettings.service
import gdata.gauth
from gdocsaudit.tools import get_oauth_client, revoke_oauth_client
import batch.handlers


import logging
import itertools

import logging
import random
import traceback
import itertools
import urllib
from copy import copy
from datetime import datetime
from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.utils import simplejson
from gapps import enqueue
from google.appengine.ext import db
from gapps.batch.utils import get_batch_id, chunk_it, get_delay, register_handler
from gapps.models import BatchChunk, BatchOperation, DomainSetup,DomainUser, TrackingValues, ReportingValues
from gapps.models import BatchUnitError, NumDocSetup, DocTypeSetup, ShareSetup, ServiceHelper
from gdata.client import RequestError
from gdocsaudit import docutils, tools
from google.appengine.api import mail, memcache
from gapps.docnames import doclist
from gapps.usernames import user_list
from gdata.docs.data import DATA_KIND_SCHEME
import gdata.docs.data
import gdata.apps.service
import gdata.apps.adminsettings.service
from gapps.batch.handlers import BaseHandler, BatchChunk, BatchOperation, BatchUnitError


secret = None
service = None

@requires_domain_oid_admin
def index(request, domain):
    ds = DomainSetup.get_for_domain(domain)

    if not ds.scan_status:
        if request.method == "POST":
            createdocsform = CreateDocsForm(request.POST)
            internalsharesettingsform = InternalShareSettingsForm(domain, request.POST)
            externalsharesettingsform = ExternalShareSettingsForm(domain, request.POST)
            externalusersform = ExternalUsersForm(domain, request.POST)
            doctypesettingsform = DocTypeSettingsForm(domain, request.POST)
            createusersform = CreateUsersForm(domain,request.POST)
            numdocsettingsform = NumDocSettingsForm(domain, request.POST)

            if createdocsform.is_valid() and \
               internalsharesettingsform.is_valid() and\
               externalsharesettingsform.is_valid() and\
               externalusersform.is_valid() and\
               doctypesettingsform.is_valid() and \
               createusersform.is_valid() and\
               numdocsettingsform.is_valid():

                #TODO create setup entities

                shares20to22 = internalsharesettingsform.cleaned_data['shares20to22']
                shares15to20 = internalsharesettingsform.cleaned_data['shares15to20'] + shares20to22
                shares10to15 = internalsharesettingsform.cleaned_data['shares10to15'] + shares15to20
                shares5to10 = internalsharesettingsform.cleaned_data['shares5to10'] + shares10to15
                shares3to5 = internalsharesettingsform.cleaned_data['shares3to5'] + shares5to10
                shares1to3 = internalsharesettingsform.cleaned_data['shares1to3'] + shares3to5
                shares0 = internalsharesettingsform.cleaned_data['shares0'] + shares1to3


                outsideuser1 = externalusersform.cleaned_data['outsideuser1']
                outsideuser2 = externalusersform.cleaned_data['outsideuser2']
                sharesoutside1 = externalsharesettingsform.cleaned_data['sharesoutside1']
                sharesoutside2 = externalsharesettingsform.cleaned_data['sharesoutside2']


                #TODO don't hard code these values, use settings.py or something
                if createdocsform.cleaned_data['shareexternal']:
                    if not outsideuser1:
                        outsideuser1 = "john.smith@externaluser1.com"
                    if not outsideuser2:
                        outsideuser2 = "externalcloudlockuser2@gmail.com"
                    if not sharesoutside1:
                        sharesoutside1 = 10
                    if not sharesoutside2:
                        sharesoutside2 = 10
                else:
                    sharesoutside1 = 0
                    sharesoutside2 = 0


                sharesetup = ShareSetup(key_name = domain,
                                        outsideuser1 = outsideuser1,
                                        outsideuser2 = outsideuser2,
                                        shares20to22 = shares20to22,
                                        shares15to20 = shares15to20,
                                        shares10to15 = shares10to15,
                                        shares5to10 = shares5to10,
                                        shares3to5 = shares3to5,
                                        shares1to3 = shares1to3,
                                        shares0 = shares0,
                                        sharespublic = externalsharesettingsform.cleaned_data['sharespublic'],
                                        sharesdomain = externalsharesettingsform.cleaned_data['sharesdomain'] + externalsharesettingsform.cleaned_data['sharespublic'],
                                        sharesoutside1 = sharesoutside1,
                                        sharesoutside2 = sharesoutside2,
                                        shareexternal = createdocsform.cleaned_data['shareexternal'])
                sharesetup.put()

                numdocsetup_old = NumDocSetup.get_by_key_name(domain)

                numdocs300to125 = numdocsettingsform.cleaned_data['numdocs300to125']
                numdocs125to75 = numdocsettingsform.cleaned_data['numdocs125to75'] + numdocs300to125
                numdocs75to25 = numdocsettingsform.cleaned_data['numdocs75to25'] + numdocs125to75
                numdocs25to10 = numdocsettingsform.cleaned_data['numdocs25to10'] + numdocs75to25
                numdocs10to5 = numdocsettingsform.cleaned_data['numdocs10to5'] + numdocs25to10
                numdocs5to1 = numdocsettingsform.cleaned_data['numdocs5to1'] + numdocs10to5

                userlimit = createdocsform.cleaned_data['userlimit']
                progress_total = userlimit
                #TODO currently always runs to the user set limit
                runtolimit = True
#                runtolimit = createdocsform.cleaned_data['runtolimit']
#                if runtolimit == 'auto':
#                    runtolimit = False
#                else:
#                    runtolimit = True
                doccount_old = numdocsetup_old.doccount if numdocsetup_old else 0
                userlimit += doccount_old
                logging.info("userlimit: %s and doccount_old: %s" % (userlimit, doccount_old))

                numdocsetup = NumDocSetup(key_name=domain,
                                          doccount = doccount_old,
                                          numdocs300to125 = numdocs300to125,
                                          numdocs125to75 = numdocs125to75,
                                          numdocs75to25 = numdocs75to25,
                                          numdocs25to10 = numdocs25to10,
                                          numdocs10to5 = numdocs10to5,
                                          numdocs5to1 = numdocs5to1,
                                          userlimit = userlimit,
                                          runtouserlimit = runtolimit,
                                          progress_doccount = 0,
                                          progress_total = progress_total)
                numdocsetup.put()


                docratio = doctypesettingsform.cleaned_data['docratio']
                spreadratio = doctypesettingsform.cleaned_data['spreadratio'] + docratio
                presratio = doctypesettingsform.cleaned_data['presratio'] + spreadratio
                pdfratio = doctypesettingsform.cleaned_data['pdfratio'] + presratio
                folderratio = doctypesettingsform.cleaned_data['folderratio'] + pdfratio


                doctypesetup = DocTypeSetup(key_name=domain,
                                            docratio = docratio,
                                            spreadratio = spreadratio,
                                            presratio = presratio,
                                            pdfratio = pdfratio,
                                            folderratio = folderratio)
                doctypesetup.put()

                num = createusersform.cleaned_data['num_users']

                ds = DomainSetup.get_for_domain(domain)
                ds.email_sent = True
                ds.users_to_create = num
                #ds.start_create_docs = "Yes"
                #ds.scan_status = "docs"
                #ds.next_user_url = models.SCAN_START_MARKER
                ds.put()

                #TODO get and create setup values here

                #TODO start user scan here


                #username = createusersform.cleaned_data['hidden1']
                #password = createusersform.cleaned_data['hidden2']

                #if createusersform.cleaned_data['hidden3']:

                #If number of users is set to 0 then skip oauth and set scope to all
                if num == 0:
                    if createusersform.cleaned_data['create_for_all']:
                        scope = 'all'
                    else:
                        scope = 'created'


                    kwargs = {
                        'users_requested': str(ds.users_to_create),
                        'scope': scope,
                        'secret': '',
                    }
                    op = BatchOperation(
                        domain = domain,
                        started_by = request.oid_user.username,
                        op_name = 'createusers',
                        op_args = list(itertools.chain(*kwargs.items()))
                    )
                    op.put()

                    batch_id = op.key().id()

                    #ds = DomainSetup.get_for_domain(domain)
                    #ds.scan_status = "users"
                    #ds.put()


                    enqueue.enqueue_batch_start(batch_id)

                    batch_id='1'+domain

                    return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                        kwargs=dict(domain=domain,
                                                                    batch_id=batch_id)))

#                    kwargs = {
#                        'users_requested': str(num),
#                        'scope': scope,
#                    }
#                    op = BatchOperation(
#                        domain = domain,
#                        started_by = request.oid_user.username,
#                        op_name = 'createusers',
#                        op_args = list(itertools.chain(*kwargs.items()))
#                    )
#                    op.put()
#
#                    batch_id = op.key().id()
#
#                    ds = DomainSetup.get_for_domain(domain)
#                    #ds.scan_status = "users"
#                    #ds.put()
#
#
#                    enqueue.enqueue_batch_start(batch_id)
#
#                    batch_id='1'+domain
#
#                    return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
#                                                        kwargs=dict(domain=domain,
#                                                                    batch_id=batch_id)))
                #TODO check if access token is valid, if not redirect to get oauth
                return HttpResponseRedirect(reverse("gapps-domain-oauth",
                                                    kwargs=dict()) + "?domain=" + domain)





        else:
            createdocsform = CreateDocsForm()
            internalsharesettingsform = InternalShareSettingsForm(domain)
            externalsharesettingsform = ExternalShareSettingsForm(domain)
            externalusersform = ExternalUsersForm(domain)
            doctypesettingsform = DocTypeSettingsForm(domain)
            createusersform = CreateUsersForm(domain)
            numdocsettingsform = NumDocSettingsForm(domain)
    else:
        batch_id='1'+domain
        if ds.scan_status == "docs":


            return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                kwargs=dict(domain=domain,
                                                            batch_id=batch_id)))
        elif ds.scan_status == "users":
            return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                kwargs=dict(domain=domain,
                                                            batch_id=batch_id)))
        elif ds.scan_status == "delete":
            return HttpResponseRedirect(reverse("gapps-domain-status-delete-docs",
                                         kwargs=dict(domain=domain,
                                                     batch_id=batch_id)))

    users_created = ds.user_created_count
    numdocsetup = NumDocSetup.get_by_key_name(domain)

    return render_to_response(
        "gapps/wizard.html",
        {'domain': domain,
         'user': request.oid_user,
         'email': request.oid_user.email,
         'users_created': users_created,
         'docs_created': numdocsetup.doccount if numdocsetup else 0,
         'createdocsform': createdocsform,
         'internalsharesettingsform': internalsharesettingsform,
         'externalsharesettingsform': externalsharesettingsform,
         'externalusersform': externalusersform,
         'doctypesettingsform': doctypesettingsform,
         'createusersform': createusersform,
         'numdocsettingsform': numdocsettingsform},
        RequestContext(request))

# handle openid logout
def logout(request, domain):
    url = users.create_logout_url(dest_url='https://www.google.com/a/cpanel/' + domain)
    return HttpResponseRedirect(redirect_to=url)

@requires_domain_oid_admin
def domain_create_docs(request, domain):

    #TODO totally need to figure out this whole form thing and how to get owner info there


#    if request.method == "POST":

#        ds = DomainSetup.get_for_domain(domain)

        #ds.start_create_docs = "Yes"
        #ds.scan_status = "docs"
        #ds.next_user_url = models.SCAN_START_MARKER
        #ds.put()

        #TODO get and create setup values here

        #TODO start user scan here

        #enqueue.enqueue_domain_user_crawl(domain, request.oid_user.username, batch_id='1'+domain, transactional=False)

#        kwargs = {
#            'notify':'',
#            'action':'createdocs',
#            'scope':'created'
#        }
#        op = BatchOperation(
#            domain = domain,
#            started_by = request.oid_user.username,
#            op_name = 'getusers',
#            op_args = list(itertools.chain(*kwargs.items()))
#        )
#        op.put()

#        batch_id = op.key().id()

#        enqueue.enqueue_batch_start(batch_id)


#        batch_id='1'+domain

#        return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
#                                                kwargs=dict(domain=domain,
#                                                            batch_id=batch_id)))
    action = 'createdocs'

    opargs = {
        'started_by': request.oid_user.username,
        'scope': 'all',
        'action': action,
        }
    op = units.operation('populator.getusers.GetUsers', domain=domain, opargs=opargs)
    #op = units.operation('populator.sharedocs.ShareDocs', domain=domain, opargs=opargs)
    op.start()

    #enqueue.enqueue_batch_start(batch_id)
    return HttpResponse("OK")

#    return HttpResponse("Not OK")

@requires_domain_oid_admin
def domain_create_users(request, domain):

    client = get_oauth_client(request.build_absolute_uri())

    revoke_oauth_client(client)

    return HttpResponse("OK")


#    if request.method == "POST":
#        num = request.REQUEST.get('numusers')
#        username = request.REQUEST.get('username')
#        password = request.REQUEST.get('password')
#        try:
#            client = gdata.apps.adminsettings.service.AdminSettingsService(email='@'.join((username,domain)), domain=domain, password=password)
#            client.ProgrammaticLogin()
#            max_users = client.GetMaximumNumberOfUsers()
#        except (RequestError, AppsForYourDomainException), e:
#            #TODO have this return to a page explaining what is wrong and what the error is
#            logging.warn(e.args)
#            return render_to_response(
#                "gapps/create_users_failed.html",
#                {'domain': domain,
#                'user': request.oid_user,
#                'email': request.oid_user.email},
#                RequestContext(request))
#        except BadAuthentication, e:
#            #TODO need to return this person to the page with a warning about bad username/password
#            return HttpResponse("Not OK")
#
#        kwargs = {
#            'username': username,
#            'password': password,
#            'users_requested': num,
#        }
#        op = BatchOperation(
#            domain = domain,
#            started_by = request.oid_user.username,
#            op_name = 'createusers',
#            op_args = list(itertools.chain(*kwargs.items()))
#        )
#        op.put()
#
#        batch_id = op.key().id()
#
#        ds = DomainSetup.get_for_domain(domain)
#        #ds.scan_status = "users"
#        #ds.put()
#
#
#        enqueue.enqueue_batch_start(batch_id)
#
#        return HttpResponseRedirect(reverse("gapps-domain-status-create-users",
#                                                kwargs=dict(domain=domain,
#                                                            batch_id=batch_id)))


@requires_domain_oid_admin
def domain_delete_docs(request, domain):
    #if request.method == "POST":
    #kwargs = {
    #    'notify':'',
    #    'action':'deletedocs',
    #    'scope':'all',
    #}
    #op = BatchOperation(
    #    domain = domain,
    #    started_by = request.oid_user.username,
    #    op_name = 'getusers',
    #    op_args = list(itertools.chain(*kwargs.items()))
    #)
    #op.put()

    #batch_id = op.key().id()

    #ds = DomainSetup.get_for_domain(domain)
    ##ds.scan_status = "delete"
    ##ds.put()
    owner = request.GET.get('owner',None)
    if owner:
        opargs = {
            'owner': owner,
            }
        op = units.operation('populator.deletedocs.DeleteDocs', domain=domain, opargs=opargs)
        #op = units.operation('populator.sharedocs.ShareDocs', domain=domain, opargs=opargs)
        op.start()

        #enqueue.enqueue_batch_start(batch_id)
        return HttpResponse("OK")


    action = 'deletedocs'

    opargs = {
        'started_by': request.oid_user.username,
        'scope': 'all',
        'action': action,
        }
    op = units.operation('populator.getusers.GetUsers', domain=domain, opargs=opargs)
    #op = units.operation('populator.sharedocs.ShareDocs', domain=domain, opargs=opargs)
    op.start()

    #enqueue.enqueue_batch_start(batch_id)
    return HttpResponse("OK")
    #return HttpResponseRedirect(reverse("gapps-domain-status-delete-docs",
    #                                     kwargs=dict(domain=domain,
    #                                                 batch_id=batch_id)))

    


    #return HttpResponse("Not OK")

@requires_domain_oid_admin
def domain_create_sites(request, domain):
    #if request.method == "POST":
    kwargs = {
        'notify':'',
        'action':'createsites',
        'scope':'all',
    }
    op = BatchOperation(
        domain = domain,
        started_by = request.oid_user.username,
        op_name = 'getusers',
        op_args = list(itertools.chain(*kwargs.items()))
    )
    op.put()

    batch_id = op.key().id()

    ds = DomainSetup.get_for_domain(domain)
    #ds.scan_status = "delete"
    #ds.put()

    enqueue.enqueue_batch_start(batch_id)
    return HttpResponse("OK")
    #return HttpResponseRedirect(reverse("gapps-domain-status-delete-docs",
    #                                     kwargs=dict(domain=domain,
    #                                                 batch_id=batch_id)))




def _batch_status_info(batch):
    from gapps.batch import get_handler

    handler = get_handler(batch)

    progress = handler.progress()

    num_done = len(progress["done"])
    num_pending = len(progress["pending"])
    num_error = len(progress["error"])
    num_skipped = len(progress["skipped"])
    num_done_or_error = num_done + num_error + num_skipped
    num_total = int(batch.kwargs.get('total', num_done_or_error+num_pending))

    if num_total:
        progress_pct = int(100 * num_done_or_error / num_total)
    else:
        progress_pct = 0


    logging.info("pct, total, done_or_error, pending: %s,%s,%s,%s" % (progress_pct,num_total,num_done_or_error,num_pending))
    
    return {
        "progress": progress,
        "num_done": num_done_or_error,
        "num_pending": num_pending,
        "num_error": num_error,
        "num_total": num_total,
        "num_skipped": num_skipped,
        "label": progress["label"],
        "op_label": progress["op_label"],
        "label_verbose": progress["label_verbose"],
        "progress_pct": progress_pct,
        "is_processing": bool(batch.finished_on is None),
        "args_description": handler.args_description(),
        }

@requires_domain_oid_admin
def domain_status(request, domain, batch_id):
    #TODO channel api testing
    id = domain + "status"
    token = channel.create_channel(id)

    logging.info("Token created")

    #context['token'] = token
    context = {
        'domain': domain,
        'token': token,
    }

    return render_to_response("gapps/status.html",
                              context,
                              RequestContext(request))

@requires_domain_oid_admin
def domain_status_json(request, domain, batch_id):
    batch = BatchOperation.objects.get_by_id(int(batch_id))
    if not(batch and batch.domain == domain):
        return HttpResponseForbidden("wrong domain")

    context = _batch_status_info(batch)

    return HttpResponse(simplejson.dumps(context),
                        mimetype='text/javascript')


@requires_domain_oid_admin
def domain_status_create_docs(request, domain, batch_id):


    #TODO channel api testing
    id = domain + "status"
    token = channel.create_channel(id)

    logging.info("Token created")

    ds = DomainSetup.get_for_domain(domain)
    users_created = ds.user_created_count
    numdocsetup = NumDocSetup.get_by_key_name(domain)

    #context['token'] = token
    context = {
        'domain': domain,
        'token': token,
        'users_created': users_created,
        'docs_created': numdocsetup.doccount if numdocsetup else 0,

    }

    return render_to_response("gapps/status.html",
                              context,
                              RequestContext(request))

@requires_domain_oid_admin
def domain_status_create_users(request, domain, batch_id):


    #TODO channel api testing
    id = domain + "status"
    token = channel.create_channel(id)

    logging.info("Token created")

    #context['token'] = token
    context = {
        'domain': domain,
        'token': token
    }

    return render_to_response("gapps/status_create_users.html",
                              context,
                              RequestContext(request))


@requires_domain_oid_admin
def domain_status_delete_docs(request, domain, batch_id):


    #TODO channel api testing
    id = domain + "deletedocs"
    token = channel.create_channel(id)

    logging.info("Token created")

    #context['token'] = token
    context = {
        'domain': domain,
        'token': token
    }

    return render_to_response("gapps/status_delete_docs.html",
                              context,
                              RequestContext(request))



@requires_domain_oid_admin
def domain_user_crawl(request, domain):

    #TODO totally need to figure out this whole form thing and how to get owner info there



    kwargs = {
        'notify':'',
    }
    op = BatchOperation(
        domain = domain,
        started_by = request.oid_user.username,
        op_name = 'getusers',
        op_args = list(itertools.chain(*kwargs.items()))
    )
    op.put()

    batch_id = op.key().id()

    enqueue.enqueue_batch_start(batch_id)

    return HttpResponse("OK")

@requires_domain_oid_admin
def domain_wizard_learn_more(request, domain):
    return render_to_response(
                "gapps/create_users_failed.html",
                {'domain': domain,
                'user': request.oid_user,
                'email': request.oid_user.email},
                RequestContext(request))



@requires_domain_oid_admin
def domain_status_error(request, domain):


    if request.method == "POST":

        if request.POST.get("hidden1"):
            scope = 'all'


            logging.info("scope: %s     users_requested: %s" % (scope, "0"))

            ds = DomainSetup.get_for_domain(domain)
            ds.email_sent = False
            ds.put()

            kwargs = {
                'username': '',
                'password': '',
                'users_requested': '0',
                'scope': scope,
            }
            op = BatchOperation(
                domain = domain,
                started_by = request.oid_user.username,
                op_name = 'createusers',
                op_args = list(itertools.chain(*kwargs.items()))
            )
            op.put()

            batch_id = op.key().id()

            ds = DomainSetup.get_for_domain(domain)
            #ds.scan_status = "users"
            #ds.put()


            enqueue.enqueue_batch_start(batch_id)

            batch_id='1'+domain

            return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                kwargs=dict(domain=domain,
                                                            batch_id=batch_id)))



    return HttpResponseRedirect(reverse("gapps-index",
                                        kwargs=dict(domain=domain)))


@requires_domain_oid_admin
def domain_wizard(request, domain):

    ds = DomainSetup.get_for_domain(domain)

    if not ds.scan_status:
        if request.method == "POST":
            createdocsform = CreateDocsForm(request.POST)
            internalsharesettingsform = InternalShareSettingsForm(domain, request.POST)
            externalsharesettingsform = ExternalShareSettingsForm(domain, request.POST)
            externalusersform = ExternalUsersForm(domain, request.POST)
            doctypesettingsform = DocTypeSettingsForm(domain, request.POST)
            createusersform = CreateUsersForm(domain,request.POST)
            numdocsettingsform = NumDocSettingsForm(domain, request.POST)

            if createdocsform.is_valid() and \
               internalsharesettingsform.is_valid() and\
               externalsharesettingsform.is_valid() and\
               externalusersform.is_valid() and\
               doctypesettingsform.is_valid() and \
               createusersform.is_valid() and\
               numdocsettingsform.is_valid():

                #TODO create setup entities

                shares20to22 = internalsharesettingsform.cleaned_data['shares20to22']
                shares15to20 = internalsharesettingsform.cleaned_data['shares15to20'] + shares20to22
                shares10to15 = internalsharesettingsform.cleaned_data['shares10to15'] + shares15to20
                shares5to10 = internalsharesettingsform.cleaned_data['shares5to10'] + shares10to15
                shares3to5 = internalsharesettingsform.cleaned_data['shares3to5'] + shares5to10
                shares1to3 = internalsharesettingsform.cleaned_data['shares1to3'] + shares3to5
                shares0 = internalsharesettingsform.cleaned_data['shares0'] + shares1to3


                outsideuser1 = externalusersform.cleaned_data['outsideuser1']
                outsideuser2 = externalusersform.cleaned_data['outsideuser2']
                sharesoutside1 = externalsharesettingsform.cleaned_data['sharesoutside1']
                sharesoutside2 = externalsharesettingsform.cleaned_data['sharesoutside2']


                #TODO don't hard code these values, use settings.py or something
                if createdocsform.cleaned_data['shareexternal']:
                    if not outsideuser1:
                        outsideuser1 = "john.smith@externaluser1.com"
                    if not outsideuser2:
                        outsideuser2 = "externalcloudlockuser2@gmail.com"
                    if not sharesoutside1:
                        sharesoutside1 = 10
                    if not sharesoutside2:
                        sharesoutside2 = 10
                else:
                    sharesoutside1 = 0
                    sharesoutside2 = 0


                sharesetup = ShareSetup(key_name = domain,
                                        outsideuser1 = outsideuser1,
                                        outsideuser2 = outsideuser2,
                                        shares20to22 = shares20to22,
                                        shares15to20 = shares15to20,
                                        shares10to15 = shares10to15,
                                        shares5to10 = shares5to10,
                                        shares3to5 = shares3to5,
                                        shares1to3 = shares1to3,
                                        shares0 = shares0,
                                        sharespublic = externalsharesettingsform.cleaned_data['sharespublic'],
                                        sharesdomain = externalsharesettingsform.cleaned_data['sharesdomain'] + externalsharesettingsform.cleaned_data['sharespublic'],
                                        sharesoutside1 = sharesoutside1,
                                        sharesoutside2 = sharesoutside2,
                                        shareexternal = createdocsform.cleaned_data['shareexternal'])
                sharesetup.put()

                numdocsetup_old = NumDocSetup.get_by_key_name(domain)

                numdocs300to125 = numdocsettingsform.cleaned_data['numdocs300to125']
                numdocs125to75 = numdocsettingsform.cleaned_data['numdocs125to75'] + numdocs300to125
                numdocs75to25 = numdocsettingsform.cleaned_data['numdocs75to25'] + numdocs125to75
                numdocs25to10 = numdocsettingsform.cleaned_data['numdocs25to10'] + numdocs75to25
                numdocs10to5 = numdocsettingsform.cleaned_data['numdocs10to5'] + numdocs25to10
                numdocs5to1 = numdocsettingsform.cleaned_data['numdocs5to1'] + numdocs10to5

                userlimit = createdocsform.cleaned_data['userlimit']
                if userlimit == 0:
                    runtolimit = False
                else:
                    runtolimit = True

                numdocsetup = NumDocSetup(key_name=domain,
                                          doccount = numdocsetup_old.doccount if numdocsetup_old else 0,
                                          numdocs300to125 = numdocs300to125,
                                          numdocs125to75 = numdocs125to75,
                                          numdocs75to25 = numdocs75to25,
                                          numdocs25to10 = numdocs25to10,
                                          numdocs10to5 = numdocs10to5,
                                          numdocs5to1 = numdocs5to1,
                                          userlimit = userlimit,
                                          runtouserlimit = runtolimit)
                numdocsetup.put()


                docratio = doctypesettingsform.cleaned_data['docratio']
                spreadratio = doctypesettingsform.cleaned_data['spreadratio'] + docratio
                presratio = doctypesettingsform.cleaned_data['presratio'] + spreadratio
                pdfratio = doctypesettingsform.cleaned_data['pdfratio'] + presratio
                folderratio = doctypesettingsform.cleaned_data['folderratio'] + pdfratio


                doctypesetup = DocTypeSetup(key_name=domain,
                                            docratio = docratio,
                                            spreadratio = spreadratio,
                                            presratio = presratio,
                                            pdfratio = pdfratio,
                                            folderratio = folderratio)
                doctypesetup.put()

                ds = DomainSetup.get_for_domain(domain)

                #ds.start_create_docs = "Yes"
                #ds.scan_status = "docs"
                #ds.next_user_url = models.SCAN_START_MARKER
                #ds.put()

                #TODO get and create setup values here

                #TODO start user scan here

                num = createusersform.cleaned_data['num_users']
                username = createusersform.cleaned_data['hidden1']
                password = createusersform.cleaned_data['hidden2']

                if createusersform.cleaned_data['create_for_all']:
                    scope = 'all'
                else:
                    scope = 'created'


                kwargs = {
                    'username': username,
                    'password': password,
                    'users_requested': str(num),
                    'scope': scope,
                }
                op = BatchOperation(
                    domain = domain,
                    started_by = request.oid_user.username,
                    op_name = 'createusers',
                    op_args = list(itertools.chain(*kwargs.items()))
                )
                op.put()

                batch_id = op.key().id()

                ds = DomainSetup.get_for_domain(domain)
                #ds.scan_status = "users"
                #ds.put()


                enqueue.enqueue_batch_start(batch_id)

                batch_id='1'+domain

                return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                    kwargs=dict(domain=domain,
                                                                batch_id=batch_id)))



        else:
            createdocsform = CreateDocsForm()
            internalsharesettingsform = InternalShareSettingsForm(domain)
            externalsharesettingsform = ExternalShareSettingsForm(domain)
            externalusersform = ExternalUsersForm(domain)
            doctypesettingsform = DocTypeSettingsForm(domain)
            createusersform = CreateUsersForm(domain)
            numdocsettingsform = NumDocSettingsForm(domain)
    else:
        batch_id='1'+domain
        if ds.scan_status == "docs":


            return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                kwargs=dict(domain=domain,
                                                            batch_id=batch_id)))
        elif ds.scan_status == "users":
            return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                                kwargs=dict(domain=domain,
                                                            batch_id=batch_id)))
        elif ds.scan_status == "delete":
            return HttpResponseRedirect(reverse("gapps-domain-status-delete-docs",
                                         kwargs=dict(domain=domain,
                                                     batch_id=batch_id)))

    users_created = ds.user_created_count
    numdocsetup = NumDocSetup.get_by_key_name(domain)

    return render_to_response(
        "gapps/wizard.html",
        {'domain': domain,
         'user': request.oid_user,
         'email': request.oid_user.email,
         'users_created': users_created,
         'docs_created': numdocsetup.doccount if numdocsetup else 0,
         'createdocsform': createdocsform,
         'internalsharesettingsform': internalsharesettingsform,
         'externalsharesettingsform': externalsharesettingsform,
         'externalusersform': externalusersform,
         'doctypesettingsform': doctypesettingsform,
         'createusersform': createusersform,
         'numdocsettingsform': numdocsettingsform},
        RequestContext(request))


# The domain_setup view is loaded during the app install process, and is
# where we will want to ask the installing user for preparatory information
# (sales lead form, and pricing/license sale). What we can do is kick off
# the domain's first report as soon as the first admin hits this page; that
# will allow us to display a moving "report in progress" bar alongside the
# sales lead form, even using a real #users figure.
#
# Probably this page should be rendered whenever an admin is logged in and
# there is not yet a completed sales lead entry (maybe this gets added as a
# BooleanProperty on DomainSetup?).  The main difference between cases where
# this url is loaded from the Google app setup wizard vs. from a regular
# admin visit is that the callback URL will not be provided locally; in
# # those cases, user should simply be redirected to domain_admin_report.
# @requires_domain_oid_admin
# def domain_setup(request, domain):
#     return render_to_response("gapps/domain_setup.html",
#                               { "ds": request.domain_setup,
#                                 "domain": domain,
#                                 "callback": request.REQUEST.get("callback"),
#                                 },
#                               RequestContext(request))

def domain_setup(request, domain):

    # Get/create the DS directly here.  If the following method returns None,
    # then either the user is not an admin or this app hasn't been granted API
    # access yet; we'll report that on the setup page.
    #ds = DomainSetup.get_for_domain(domain,  ## DOH no user yet!

    from google.appengine.api import users
    u = users.get_current_user()

    #import sys; [ setattr(sys, attr, getattr(sys, '__%s__' % attr)) for attr in ('stdin', 'stdout', 'stderr') ]; import pdb;pdb.set_trace()

    ds = None # by default there is no DomainSetup yet

    if u:
        # Basically do the same thing we do in @requires_domain_oid_admin,
        # but if it doesn't work simply leave the ds at None instead of
        # returning a redirect response to openid login.
        domain = domain.lower()

        user_email = u.email()

        if user_email.lower().endswith("@"+domain):
            request.oid_user = u

            chars_to_strip = len("@"+domain)
            u.username = u.email()[:-chars_to_strip]

            ds = DomainSetup.get_for_domain_as_admin(domain, u)
    else:
        user_email = ""

    callback = request.REQUEST.get("callback")
    step = request.REQUEST.get("step")

    if callback and step == "2":
        template = "gapps/domain_setup_step2.html"
    else:
        template = "gapps/domain_setup_step1.html"


    return render_to_response(template, #"gapps/domain_setup.html",
                              { "ds": ds,
                                "domain": domain,
                                "callback": callback,
                                "trial_days": settings.DEFAULT_EXPIRATION_DELAY.days,
                                "step_2_url": request.build_absolute_uri()+"&step=2",
                                "form_email": user_email,
                                },
                              RequestContext(request))

def domain_support(request):
    return render_to_response("gapps/domain_support.html", { },
                              RequestContext(request))

def domain_deletion_policy(request):
    return render_to_response("gapps/domain_deletion_policy.html", { },
                              RequestContext(request))


#3-legged OAuth functions

@requires_domain_oid_admin
def domain_test(request, domain):
    return render_to_response(
                "gapps/index.html",
                {'domain': domain,
                'user': request.oid_user,
                'email': request.oid_user.email},
                RequestContext(request))

#@requires_domain_oid_admin
def domain_oauth(request):

    #TODO somewhere we need to check if access token is valid and only then get a new one

    from google.appengine.api import users

    domain = request.GET.get('domain','')
    global service
    global secret
    INIT = {
    'APP_NAME': settings.API_CLIENT_SOURCE,
    'SCOPES': ['https://apps-apis.google.com/a/feeds/', 'https://apps-apis.google.com/a/feeds/domain/']
    }

    ds = DomainSetup.get_for_domain(domain)

    if request.GET.get('oauth_verifier', None):

        consumer_key = "aprigoninja8.appspot.com"
        consumer_secret = "_Nd9uUq52h_7MWCfSfX2l5JN"

        service.SetOAuthInputParameters(
            gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
            consumer_key, consumer_secret=consumer_secret)

        oauth_token = gdata.auth.OAuthTokenFromUrl(request.build_absolute_uri())
        if oauth_token:
            oauth_token.secret = secret
            oauth_token.oauth_input_params = service.GetOAuthInputParameters()
            oauth_token.scopes = INIT['SCOPES']
            service.SetOAuthToken(oauth_token)
            # Exchange the request token for an access token
            oauth_verifier = request.GET.get('oauth_verifier', '')
            access_token = service.UpgradeToOAuthAccessToken(
                oauth_verifier=oauth_verifier)
            # Store access_token to the service token_store for later access
            if access_token:
                service.token_store.add_token(access_token)
                service.current_token = access_token
                service.SetOAuthToken(access_token)
                logging.info("access_token: %s" % access_token)
                sh = ServiceHelper(key_name = domain, access_token = pickle.dumps(access_token))
                sh.put()

                try:
                    domain_service = gdata.apps.adminsettings.service.AdminSettingsService(source=settings.API_CLIENT_SOURCE, domain=domain)
                    domain_service.token_store.add_token(access_token)
                    domain_service.current_token = access_token
                    domain_service.SetOAuthToken(access_token)
                    max_users = domain_service.GetMaximumNumberOfUsers()
                    
                    
                    
                except AppsForYourDomainException, e:

                   #context['token'] = token
                   #id = domain + "status"
                   #token = channel.create_channel(id)

                   context = {
                       'domain': domain,
                       #'token': token,
                       'open_error_dialog':True,
                       }

                   return render_to_response("gapps/status.html",
                                             context,
                                             RequestContext(request))


        #batch.handlers.service = service


        ds = DomainSetup.get_for_domain(domain)
        ds.email_sent = False
        #ds.start_create_docs = "Yes"
        #ds.scan_status = "docs"
        #ds.next_user_url = models.SCAN_START_MARKER
        ds.put()

        u = users.get_current_user()


#            unit = "DAN.REED3"
#            names = unit.split('.')
#            user_name = unit
#            family_name = names[1]
#            given_name = names[0]
#            password = "cl0udl0ck"
#            new_user = None
#            try:
#
#                new_user = service.CreateUser(user_name, family_name, given_name, password, suspended='false', quota_limit=gdata.apps.service.DEFAULT_QUOTA_LIMIT,password_hash_function=None)
#                #new_user = service.RetrieveUser("admin")
#                #logging.info(new_user.username)
#                #feed = service.GetDocumentListFeed()
#
#            except gdata.apps.service.AppsForYourDomainException, e:
#                #if entity exists break {'status': 400, 'body': '<?xml version="1.0" encoding="UTF-8"?>\r\n<AppsForYourDomainErrors>\r\n  <error errorCode="1300" invalidInput="JOHN.WILLIAMS" reason="EntityExists" />\r\n</AppsForYourDomainErrors>\r\n\r\n', 'reason': 'Bad Request'}
#                logging.warn(e.args)
#                if e.reason == "EntityExists":
#                    logging.warn("User already exists")
#                    #make sure we cover the odd case where a user already exists
#                    #if we don't have a domain user value create it and take credit for creating it
#                    #TODO might not be the best choice fix this later
#                    pass
#                else:
#                    raise
#            #return HttpResponseRedirect(reverse("gapps-domain-test",
#            #                                            kwargs=dict(domain=domain)))
#          #return HttpResponse("OK")
#
#            count = ds.users_to_create
#            higher_index=None
#            num_chunks = 0
#            chunk_size = 10
#
#            while True:
#
#                logging.info("Hit top of loop")
#                if count == 0:
#                    if higher_index:
#                        ds.owner_offset = higher_index
#                        ds.put()
#                    break
#
#                if count < chunk_size:
#                    current_chunk_size = count
#                else:
#                    current_chunk_size = chunk_size
#                count -= current_chunk_size
#
#                lower_index = ds.owner_offset + (num_chunks * chunk_size)
#                higher_index = (lower_index + current_chunk_size)
#                if(higher_index >= len(user_list)):
#                    higher_index = len(user_list) - 1
#
#                users = list(user_list[lower_index:higher_index])
#
#                units_pending = list(user_list[lower_index:higher_index])
#                unit_count = len(units_pending)
#
#                num_chunks += 1
#                logging.info('Have created chunks containing units for batch.')
#
#                enqueue.enqueue_domain_userlist(domain, u.email(), units_pending, transactional=False)
##############################
#            register_handler(CreateUsers.key, CreateUsers)
#

        chars_to_strip = len("@"+domain)
        username = u.email()[:-chars_to_strip]

        scope = 'created'

        kwargs = {
            'users_requested': str(ds.users_to_create),
            'scope': scope,
            'secret': secret,
        }
        op = BatchOperation(
            domain = domain,
            started_by = username,
            op_name = 'createusers',
            op_args = list(itertools.chain(*kwargs.items()))
        )
        op.put()

        batch_id = op.key().id()

        #ds = DomainSetup.get_for_domain(domain)
        #ds.scan_status = "users"
        #ds.put()


        enqueue.enqueue_batch_start(batch_id)

        batch_id='1'+domain

        return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                            kwargs=dict(domain=domain,
                                                        batch_id=batch_id)))

    logging.info("got here 2")
    consumer_key = "aprigoninja8.appspot.com"
    consumer_secret = "_Nd9uUq52h_7MWCfSfX2l5JN"
    service = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE, domain=domain)
    #gdata.alt.appengine.run_on_appengine(service)
    #service = gdata.docs.service.DocsService(source=settings.API_CLIENT_SOURCE)
    """Demonstrates usage of OAuth authentication mode and retrieves a list of
    documents using Document List Data API."""
    logging.info('STEP 1: Set OAuth input parameters.')
    service.SetOAuthInputParameters(
        gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
        consumer_key, consumer_secret=consumer_secret)
    logging.info('STEP 2: Fetch OAuth Request token.')
    #request_token = service.GetOAuthToken(
    #    scopes=INIT['SCOPES'], oauth_callback=request.build_absolute_uri(), consumer_key=consumer_key, consumer_secret=consumer_secret)
    request_token = service.FetchOAuthRequestToken(
        scopes=INIT['SCOPES'], oauth_callback=request.build_absolute_uri())

    secret = request_token.secret

    #gdata.gauth.AeSave(request_token, 'RequestToken')
    
    logging.info('Request Token fetched: %s' % request_token)
    logging.info('STEP 3: Set the fetched OAuth token.')
    service.SetOAuthToken(request_token)
    logging.info('OAuth request token set.')
    logging.info('STEP 4: Generate OAuth authorization URL.')

    #auth_url = request_token.generate_authorization_url(google_apps_domain=domain)
    auth_url = service.GenerateOAuthAuthorizationURL(extra_params={'hd': domain})

    logging.info('Authorization URL: %s' % auth_url)



    return HttpResponseRedirect(auth_url)

@taskqueue_only
def domain_enqueue_task_userlist(request, taskinfo, domain):# taskinfo,

    global service

    units_pending = simplejson.loads(request.POST.get('units_pending', ''))

    new_service = service

    for unit in units_pending:
        ds = DomainSetup.get_for_domain(domain)
        if ds.user_created_count > ds.user_limit:
            return



#        if True:

    #        username = chunk.kwargs['username']
    #        password = chunk.kwargs['password']
    #        client = gdata.apps.service.AppsService(email='@'.join((username,domain)), domain=domain, password=password)
    #        #client = gdata.apps.adminsettings.service(email='admin@testninjagdocs.com', domain='testninjagdocs.com', password='Apr1g0Lab')
    #        client.ProgrammaticLogin()
            #ds = DomainSetup.get_for_domain(domain)
        names = unit.split('.')
        user_name = unit
        family_name = names[1]
        given_name = names[0]
        password = "cl0udl0ck"
        new_user = None
        try:

            new_user = service.CreateUser(user_name, family_name, given_name, password, suspended='false', quota_limit=gdata.apps.service.DEFAULT_QUOTA_LIMIT,password_hash_function=None)

        except gdata.apps.service.AppsForYourDomainException, e:
            #if entity exists break {'status': 400, 'body': '<?xml version="1.0" encoding="UTF-8"?>\r\n<AppsForYourDomainErrors>\r\n  <error errorCode="1300" invalidInput="JOHN.WILLIAMS" reason="EntityExists" />\r\n</AppsForYourDomainErrors>\r\n\r\n', 'reason': 'Bad Request'}
            logging.warn(e.args)
            if e.reason == "EntityExists":
                logging.warn("User already exists")
                #make sure we cover the odd case where a user already exists
                #if we don't have a domain user value create it and take credit for creating it
                #TODO might not be the best choice fix this later
                key_name = DomainUser.make_key_name(domain, unit)
                duser = DomainUser.get_by_key_name(key_name)
                if duser is None:
                    duser = DomainUser(key_name=key_name, username=unit, domain=domain, created_by_us=True)
                    duser.put()

                    logging.info("DomainUser Value Created: %s" % unit)
                else:
                    #Make sure duser is considered created by us
                    duser.created_by_us = True
                    duser.put()
                    logging.info("DomainUser Already Exists: %s" % unit)
                pass
            else:
                raise
        if new_user:
            logging.info("New User is: %s", new_user.login.user_name)

            ds.user_created_count += 1
            ds.put()

            """Returns created/updated DomainUser object"""
            key_name = DomainUser.make_key_name(domain, unit)
            duser = DomainUser.get_by_key_name(key_name)
            if duser is None:
                duser = DomainUser(key_name=key_name, username=unit, domain=domain, created_by_us=True)
                duser.put()

                logging.info("DomainUser Value Created: %s" % unit)
            else:
                #Make sure duser is considered created by us
                duser.created_by_us = True
                duser.put()
                logging.info("DomainUser Already Exists: %s" % unit)
        else:
            logging.warn("New User not created")


        logging.info("Batch_id used for channel: %s" % domain)

        progress = dict()
        progress['progress_pct'] = int(25)
        message = simplejson.dumps(progress)
        id = domain + "status"
        try:
            channel.send_message(id, message)
        except (channel.InvalidChannelClientIdError, channel.InvalidMessageError), e:
            pass

#        if progress['progress_pct'] == 100:
#            ds = DomainSetup.get_for_domain(self.batch.domain)
#            ds.scan_status = None
#            ds.put()

    logging.info("test")

    return HttpResponse("OK")

def domain_verify(request, domain):

    global service
    global secret
    # Extract the OAuth request token from the URL
    oauth_token = gdata.auth.OAuthTokenFromUrl(request.uri)
    if oauth_token:
      oauth_token.secret = secret
      oauth_token.oauth_input_params = service.GetOAuthInputParameters()
      service.SetOAuthToken(oauth_token)
      # Exchange the request token for an access token
      oauth_verifier = request.GET.get('oauth_verifier', default_value='')
      access_token = service.UpgradeToOAuthAccessToken(
          oauth_verifier=oauth_verifier)
      # Store access_token to the service token_store for later access
      if access_token:
        service.current_token = access_token
        service.SetOAuthToken(access_token)

    return HttpResponse("OK")

def verify_google(request):
        return render_to_response("gapps/google2a8b4efed45abe2e.html", { },
                              RequestContext(request))

@requires_domain_oid_admin
def domain_create_large_exposures(request, domain):

    kwargs = {
              'secret': '',
    }
    op = BatchOperation(
        domain = domain,
        started_by = request.oid_user.username,
        op_name = 'createlargeexposures',
        op_args = list(itertools.chain(*kwargs.items()))
    )
    op.put()

    batch_id = op.key().id()

    enqueue.enqueue_batch_start(batch_id)

    return HttpResponse("OK")


import units
import batch.handlers
import populator

@requires_domain_oid_admin
def domain_units_test(request, domain):
    action = request.GET.get('action')
    logging.info("Action: " + action)
    if not action:
        return HttpResponse("NOT OK")
    #opargs = {
    #    'owner': 'keith',
    #    }
    #op = units.operation('populator.createdocs.CreateDocs', domain=domain, opargs=opargs)
    #op.start()
    logging.info(request.oid_user.username)
    opargs = {
        'started_by': request.oid_user.username,
        'scope': 'all',
        'action': action,
        }
    op = units.operation('populator.getusers.GetUsers', domain=domain, opargs=opargs)
    #op = units.operation('populator.sharedocs.ShareDocs', domain=domain, opargs=opargs)
    op.start()

    #id = self.meta.domain + ':'
    #memcache.set(id + 'modifyacl', kwargs.get('modifyacl', 0))
    #memcache.set(id + 'deletedoc', kwargs.get('deletedoc', 0))
    #memcache.set(id + 'createdoc', kwargs.get('createdoc', 0))
    #memcache.set(id + 'removepublic', kwargs.get('removepublic', 0))
    #memcache.set(id + 'removeinternal', kwargs.get('removeinternal', 0))
    #memcache.set(id + 'removeexternal', kwargs.get('removeexternal', 0))
    #memcache.set(id + 'addpublic', kwargs.get('addpublic', 0))
    #memcache.set(id + 'addinternal', kwargs.get('addinternal', 0))
    #memcache.set(id + 'addexternal', kwargs.get('addexternal', 0))
    #memcache.set(id + 'addinternalacl', kwargs.get('addinternalacl', 0))
    #memcache.set(id + 'removeinternalacl', kwargs.get('removeinternalacl', 0))
    #memcache.set(id + 'changecontent', kwargs.get('changecontent', 0))
    #memcache.set(id + 'changetitle', kwargs.get('changetitle', 0))

    #key = domain + ':tracking'
    #tv = TrackingValues(key_name=key, 
    #                    modifyacl=1, 
    #                    removepublic=1,
    #                    removeinternal=1,
    #                    removeexternaluser=1,
    #                    addpublic=1,
    #                    addinternal=1,
    #                    addexternaluser=1,
    #                    changecontent=1,
    #                    changetitle=1,
    #                    addinternaluser=1,
    #                    removeinternaluser=1,
    #                    changeowner=1,
    #                    deletedoc=1,
    #                    createdoc=1)

    #tv.put()
    #key = domain + ':reporting'
    #rv = ReportingValues(key_name=key)
    #rv.put()
    #opargs = {
    #    'owner': 'keith',
    #    'external_user': 'john.smith@externaluser1.com',
    #    'change_owner_to': 'tull@everyoneexposure.com',
    #    }
    #op = units.operation('populator.modifydocs.ModifyDocs', domain=domain, opargs=opargs)
    #op.start()

    return HttpResponse("OK")


#####################################
# Cleaned up oauth stuff
#####################################

#@requires_domain_oid_admin
def domain_oauth_clean(request):

    #TODO somewhere we need to check if access token is valid and only then get a new one

    from google.appengine.api import users

    domain = request.GET.get('domain','')
    global service
    global secret
    INIT = {
    'APP_NAME': settings.API_CLIENT_SOURCE,
    'SCOPES': ['https://apps-apis.google.com/a/feeds/', 'https://apps-apis.google.com/a/feeds/domain/']
    }

    ds = DomainSetup.get_for_domain(domain)


### Second time through this function (see below this if statement for first time flow)
    if request.GET.get('oauth_verifier', None):

        ### Set consumer key and secret
        consumer_key = "aprigoninja8.appspot.com"
        consumer_secret = "_Nd9uUq52h_7MWCfSfX2l5JN"

        ### Set the input parameters for the service - service is a global variable set below this if statement
        service.SetOAuthInputParameters(
            gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
            consumer_key, consumer_secret=consumer_secret)

        ### Get oauth token from the url (oauth_verifier)
        oauth_token = gdata.auth.OAuthTokenFromUrl(request.build_absolute_uri())
        if oauth_token:
            ### Set secret for oauth token from global secret variable set below
            oauth_token.secret = secret
            ### Set input parameters
            oauth_token.oauth_input_params = service.GetOAuthInputParameters()
            ### Set scopes
            oauth_token.scopes = INIT['SCOPES']
            ### Set token in the service
            service.SetOAuthToken(oauth_token)
            ### Exchange the request token for an access token
            oauth_verifier = request.GET.get('oauth_verifier', '')
            access_token = service.UpgradeToOAuthAccessToken(
                oauth_verifier=oauth_verifier)
            ### Store access_token to the service token_store for later access
            if access_token:
                ### Not sure if this works
                service.token_store.add_token(access_token)
                ### Set current token
                service.current_token = access_token
                service.SetOAuthToken(access_token)

                logging.info("access_token: %s" % access_token)
                ### Datastore entity made to store this token for later use (see gapps/batch/handlers.py do_unit in createusers)
                sh = ServiceHelper(key_name = domain, access_token = pickle.dumps(access_token))
                sh.put()

                try:
                    ### Create new service for the adminsettings API
                    domain_service = gdata.apps.adminsettings.service.AdminSettingsService(source=settings.API_CLIENT_SOURCE, domain=domain)
                    ### Set/Use the token
                    domain_service.token_store.add_token(access_token)
                    domain_service.current_token = access_token
                    domain_service.SetOAuthToken(access_token)
                    ### Finally actually use the service for something worthwhile
                    max_users = domain_service.GetMaximumNumberOfUsers()
                    
                    
                    
                except AppsForYourDomainException, e:

                    ### OH NO you were using a free domain
                   context = {
                       'domain': domain,
                       #'token': token,
                       'open_error_dialog':True,
                       }

                   return render_to_response("gapps/status.html",
                                             context,
                                             RequestContext(request))



        ### Random code for creating the batch operation that uses this service

        ds = DomainSetup.get_for_domain(domain)
        ds.email_sent = False
        #ds.start_create_docs = "Yes"
        #ds.scan_status = "docs"
        #ds.next_user_url = models.SCAN_START_MARKER
        ds.put()

        u = users.get_current_user()


        chars_to_strip = len("@"+domain)
        username = u.email()[:-chars_to_strip]

        scope = 'created'

        kwargs = {
            'users_requested': str(ds.users_to_create),
            'scope': scope,
            'secret': secret,
        }
        op = BatchOperation(
            domain = domain,
            started_by = username,
            op_name = 'createusers',
            op_args = list(itertools.chain(*kwargs.items()))
        )
        op.put()

        batch_id = op.key().id()

        #ds = DomainSetup.get_for_domain(domain)
        #ds.scan_status = "users"
        #ds.put()


        enqueue.enqueue_batch_start(batch_id)

        batch_id='1'+domain

        return HttpResponseRedirect(reverse("gapps-domain-status-create-docs",
                                            kwargs=dict(domain=domain,
                                                        batch_id=batch_id)))


### Where you go on the first time flow
    logging.info("got here 2")

### Set consumer key and secret
    consumer_key = "aprigoninja8.appspot.com"
    consumer_secret = "_Nd9uUq52h_7MWCfSfX2l5JN"

### Set service you need - global variable
    service = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE, domain=domain)
    """Demonstrates usage of OAuth authentication mode and retrieves a list of
    documents using Document List Data API."""

    logging.info('STEP 1: Set OAuth input parameters.')
    service.SetOAuthInputParameters(
        gdata.auth.OAuthSignatureMethod.HMAC_SHA1,
        consumer_key, consumer_secret=consumer_secret)

    logging.info('STEP 2: Fetch OAuth Request token.')

    request_token = service.FetchOAuthRequestToken(
        scopes=INIT['SCOPES'], oauth_callback=request.build_absolute_uri())

### Set secret global variable
    secret = request_token.secret

### Maybe look into this for saving tokens
    #gdata.gauth.AeSave(request_token, 'RequestToken')
    
    logging.info('Request Token fetched: %s' % request_token)
    logging.info('STEP 3: Set the fetched OAuth token.')
    service.SetOAuthToken(request_token)


    logging.info('OAuth request token set.')
    logging.info('STEP 4: Generate OAuth authorization URL.')
    auth_url = service.GenerateOAuthAuthorizationURL(extra_params={'hd': domain})

    logging.info('Authorization URL: %s' % auth_url)


### Send the user to the auth url which will redirect them back to the top of this function
    return HttpResponseRedirect(auth_url)

