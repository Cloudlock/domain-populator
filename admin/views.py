# admin.views

import logging
from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.conf import settings
from django import forms

from google.appengine.api import users
from google.appengine.ext import db

import datetime


from gapps.models import DomainSetup

def appengine_admin_only(view_func):
    """
    Decorator that allows only appengine admins to access the given view.
    """
    def wrapper(request, *args, **kwargs):

        current_user = users.get_current_user()

        if users.is_current_user_admin():
            request.admin_only = True
            return view_func(request, *args, **kwargs)

        else:

            # url used for open id authentication
            if current_user:
                logging.error("A non aprigo admin attempted to use: " + request.get_full_path() + "using: " + current_user.email())
                return render_to_response("admin/denied_access.html")
            else:
                url = users.create_login_url(dest_url=request.get_full_path(), _auth_domain=None, federated_identity='aprigo.com')
                return HttpResponseRedirect(redirect_to=url)

    wrapper.__doc__ = view_func.__doc__
    wrapper.__dict__ = view_func.__dict__
    return wrapper

@appengine_admin_only
def cheat(request):
    
    if request.method == "POST":

        # get email and nickname from cheat view
        fake_email = request.REQUEST.get("email")
        fake_nickname = request.REQUEST.get("nickname")

        logging.warn("Cheat login as '%s', '%s'." % (fake_nickname, fake_email))

        if fake_email and fake_nickname:

            # create a session using the beaker lib
            session = request.environ.get('beaker.session')
            session["DEBUG_AS_THIS_USER"] = dict(
                nickname=fake_nickname,
                email=fake_email)
            session.save()

            # get domain from email field in the cheat view
            domain = fake_email.rsplit("@", 1)[-1]

            logging.info('beaker session saved')
            
            return HttpResponseRedirect(reverse("gapps-index",kwargs={"domain":domain}))

    return render_to_response("admin/cheat.html", {}, RequestContext(request))
