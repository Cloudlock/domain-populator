import logging
import hashlib

from django.conf import settings
from django.utils import simplejson
from django.http import HttpResponse, HttpResponseBadRequest
from gdata.client import RequestError
from gdata.apps.service import AppsForYourDomainException
from gdata.service import BadAuthentication
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse

import gdata.apps.service
import gdata.apps.adminsettings.service

def domain_ajax_wizard_check(request, domain):
    error_msg = []
    username = request.POST.get("username")
    password = request.POST.get("password")

    try:
        client = gdata.apps.adminsettings.service.AdminSettingsService(email='@'.join((username,domain)), domain=domain, password=password)
        client.ProgrammaticLogin()
        max_users = client.GetMaximumNumberOfUsers()
    except (RequestError, AppsForYourDomainException), e:
        #TODO have this return to a page explaining what is wrong and what the error is
        logging.warn(e.args)
        #raise forms.ValidationError(mark_safe('We unfortunately cannot create users for this domain.  </br> <a href="%s">Click Here</a> to create users manually </br> Set Number of Users to create to 0 to continue <script type="text/javascript">$(document).ready(setupEndUser);$("#create_users_dialog").dialog(\'open\');</script>' % reverse("gapps-domain-wizard-error",kwargs=dict(domain=self.domain))))
        #return HttpResponseRedirect(reverse("gapps-domain-wizard-error",
        #                                   kwargs=dict(domain=self.domain)))
        error_msg.append(mark_safe('We unfortunately cannot create users for this domain.'))

    except BadAuthentication, e:
        #TODO need to return this person to the page with a warning about bad username/password
        #raise forms.ValidationError(mark_safe('The username or password you entered is invalid.<script type="text/javascript">$(document).ready(setupEndUser);$("#create_users_dialog").dialog(\'open\');</script>'))
        error_msg.append('The username or password you entered is invalid.')

    return HttpResponse(simplejson.dumps(error_msg), mimetype='text/javascript')
  