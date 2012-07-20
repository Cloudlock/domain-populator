from google.appengine.api import users
from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.conf import settings
from django.utils.http import urlquote
from google.appengine.api import mail
import logging
import re

from models import DomainSetup

def safe_repr(x):
    # apparently repr(request) can fail
    try:
        return repr(x)
    except Exception, e:
        return 'repr() failed: ' + str(e)

def taskqueue_only(view_func):
    """
    Decorator that limits the function to being called from taskqueue only,
    *if* running in production (allows regular requests during development).

    Requests from the Task Queue service contain the following HTTP headers:

        * X-AppEngine-QueueName, the name of the queue (possibly default)
        * X-AppEngine-TaskName, the name of the task, or a system-generated unique ID if no name was specified
        * X-AppEngine-TaskRetryCount, the number of times this task has been retried; for the first attempt, this value is 0

    """

    def wrapper(request, *args, **kwargs):
        if not(settings.RUNNING_IN_PRODUCTION) or request.META.get("REMOTE_ADDR","").startswith(settings.AE_TASK_IP_PREFIX):

            taskinfo = { }

            for hdr in ["QueueName",
                        "TaskName",
                        "TaskRetryCount",
                        ]:
                value = request.META.get("HTTP_X_APPENGINE_" + hdr.upper().replace("-","_"), "")
                taskinfo[hdr] = value
                logging.info("Task Queue header: %s = %s" %
                             (hdr, taskinfo[hdr]))
                if (hdr == "TaskRetryCount") and (int(value) > settings.MAX_TASKQUEUE_FAILURES):
                    # send alert mail
                    subject='%s task failed too much (%s)' % (request.path, value)
                    logging.error(subject)
                    mail.send_mail(
                        sender=settings.SERVER_EMAIL,
                        to=settings.ADMINS,
                        subject=subject,
                        body=safe_repr(request))
                    return HttpResponse('fail')
            return view_func(request, taskinfo, *args, **kwargs)

        return HttpResponseForbidden("Task queue use only.")

    wrapper.__doc__ = view_func.__doc__
    wrapper.__dict__ = view_func.__dict__
    return wrapper

def requires_domain_oid(view_func, admin_required=False, setup_if_admin=True):
    """Decorator that ensures the user is logged in via domain openID.
    
    If admin_required is True, user must be an admin.
    
    If setup_if_admin is True, user needn't be an admin, but if s/he is and
    no DomainSetup exists for the domain yet, it will be created.
    
    If login is required but not current, redirection happens.
    If login is present, request.oid_user is set to
    users.get_current_user().
    """

    def wrapper(request, domain, *args, **kwargs):

        oauth = False
        # get the passed in domain
        domain = domain.lower()
        logging.info("domain: %s" % domain)
        if domain == "oauth":
            domain = request.GET.get('domain','').lower()
            oauth = True

        #domain = request.oid_user.email.split('@')[1].lower()
        # check if we are storing a user session for testing (fake user)
        fake_user = settings.DEBUG_AS_THIS_USER
        session = request.environ.get('beaker.session')

        if session and not(fake_user):
            fake_user = session.get("DEBUG_AS_THIS_USER")

        # if we are not using a fake user then get the current user (regular flow)
        # if we are using a fake user then create a user from the beaker session info
        if fake_user:
            logging.error("Setting fake user for request: %r" % fake_user)
            fake_email = fake_user['email']
            u = users.User(email=fake_email, _auth_domain=None, federated_provider=None, federated_identity=domain)
        else:
            u = users.get_current_user()
        
        logging.info("Current user is: %r" % u)
        # check if the current user matches the domain from the url
        if u and u.email().lower().endswith("@"+domain):
            request.oid_user = u

            chars_to_strip = len("@"+domain)
            u.username = u.email()[:-chars_to_strip]

            if admin_required:
                ds = DomainSetup.get_for_domain_as_admin(domain, u)

                if not ds:

                    msg = "<p>Sorry, you must be a %s domain administrator to view this page.  (You are currently logged in as %s.)</p>  <p>Additionally, the Aprigo CloudLock for gDocs application must be installed in your domain, enabled, and able to access the APIs it requires.  This application requires the Docs and Provisioning (read-only) APIs.</p>" % (domain, u.email())
                    logging.error("Admin required; access denied on %s: %s" % (request.get_full_path(), msg))
                    return render_to_response("denied.html",
                                              {"msg":msg, "domain": domain},
                                              RequestContext(request)
                                              )
            else:
                if setup_if_admin:
                    ds = DomainSetup.get_for_domain(domain, try_setup_as_user=u)
                else:
                    ds = DomainSetup.get_for_domain(domain)

                if not ds:
                    logging.warn("Attempt to access unconfigured domain.")
                    msg = "Sorry, the domain %s is not yet configured for use in this application. A domain administrator must install the application first." % domain
                    return render_to_response("denied.html", {"msg":msg},
                                              RequestContext(request))
                    

            u.is_domain_admin = u.username in ds.administrators

            request.domain_setup = ds


            #expired_path = reverse("gapps-domain-expired", kwargs={"domain":domain})
            #if ds.is_expired() and request.path != expired_path:
            #    return HttpResponseRedirect(expired_path)

            #else:
            if oauth:
                return view_func(request, *args, **kwargs)
            return view_func(request, domain, *args, **kwargs)

        else:

            # openid authentication
            url = users.create_login_url(dest_url=request.get_full_path(), _auth_domain=None, federated_identity=domain)
            logging.info("create-login-url = " + url)
            return HttpResponseRedirect(redirect_to=url)

    wrapper.__doc__ = view_func.__doc__
    wrapper.__dict__ = view_func.__dict__
    return wrapper


def requires_domain_oid_admin(view_func):
    return requires_domain_oid(view_func, admin_required=True)

