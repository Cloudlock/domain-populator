from django.conf import settings

from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponsePermanentRedirect, get_host
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

import logging

SSL_MIDDLEWARE_ENABLED = settings.FORCE_SSL_MIDDLEWARE_ENABLED

class ForceSSL:

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not SSL_MIDDLEWARE_ENABLED or request.META.get("REMOTE_ADDR","").startswith(settings.AE_TASK_IP_PREFIX):
            return # no SSL for task queue requests

        if request.path.startswith("/static/"):
            return

        if request.is_secure():
            return

        return self._redirect(request, True) # redirect to HTTPS version

    def _redirect(self, request, secure):
        protocol = secure and "https" or "http"
        newurl = "%s://%s%s" % (protocol,
                                get_host(request),
                                request.get_full_path())

        if settings.DEBUG and request.method == 'POST':
            raise RuntimeError, \
        """Django can't perform a SSL redirect while maintaining POST data.
           Please structure your views so that redirects only occur during GETs."""

        return HttpResponsePermanentRedirect(newurl)



class CatchSpuriousErrors:
    def process_exception(self, request, exception):

        exname = type(exception).__name__
        ignore_me = False

        if exname == "Http404":
            logging.info("CatchSpuriousErrors.process_exception: ignoring 404.")
            return None

        logging.warn("CatchSpuriousErrors.process_exception: handling exception of type %s name=%s: %s" % (
                type(exception),
                exname,
                exception))

        # Broadly -- only ignore errors that came from Taskqueue:
        if request.META.get("REMOTE_ADDR","").startswith(settings.AE_TASK_IP_PREFIX):
            # First, ignore dbupdates that timed out due to deadline exc
            if request.path.startswith("/ga/t/dbupdate/") and exname in ["DeadlineExceededError", "TransactionFailedError", "TransientError"]:
                ignore_me = True
            elif request.path.startswith("/ga/t/apicall/") and exname in ["DownloadError","ResponseTooLargeError", "DeadlineExceededError", "TransactionFailedError", "TransientError"]:
                ignore_me = True


        if ignore_me:
            logging.error("IGNORED SPURIOUS ERROR!")

            return HttpResponse("A recoverable internal error occurred. This message should never reach a human; if you're a human and saw this, please contact support@aprigo.com and include the current URL: %s" % request.build_absolute_uri(), status=503) # 503 Service Temporarily Unavailable

        else:
            logging.warn("This error should result in an email to admins.")
            return None # continue with normal exception processing.
