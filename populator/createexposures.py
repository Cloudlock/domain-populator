import units
import random
import logging


from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, ShareSetup
from gapps.usernames import user_list
from gdocsaudit import docutils, tools, sitesutils
from google.appengine.api import mail, memcache

from gdata.client import RequestError

class CreateExposures(BaseHandler):
    
    concurrency = 10
    other_share_list = []
    
    def prerun(self):
        kwargs = self.meta.kwargs
        logging.info("Test")
        pass


    def iterunits(self):
        
        count = 3000
        shares = [i for i in range(count)]
        logging.info("Test2")
        for unit in shares:
            name = user_list[unit] + unit
            yield name


    def do_unit(self, unit):
        owner = 'mj' #self.meta.kwargs.get('owner')
        doc_id = 'document%3A11nOoPsGJIr6AriKOqP7dnz5e49IofXY8coopU6iSwHE' #self.meta.kwargs.get('doc_id')
        domain = self.meta.domain
        logging.info("Sharing doc with user %s", unit)
#        sharesetup = ShareSetup.get_by_key_name(domain)
        try:
            username = '@'.join((unit, domain))
            #TODO add share here
            docutils.share_user(owner, domain, doc_id, username)
        except RequestError, e:
            logging.warn(e.args)
            if e.status == 409 and "user already has access to the document" in getattr(e, 'body', ''):
                pass
            elif "emails could not be sent" in getattr(e,'body',''):
                #We experienced a case when the ownership was changed but google failed to send the notification email to
                #the new owner. We don't need to consider this case as a failure
                pass
            else:
                raise


    def op_done(self):
        # Set progress and send email if necessary
        pass



