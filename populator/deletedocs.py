import units
import logging
import time
import sys

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup
from gapps.usernames import user_list
from gdocsaudit import docutils

class DeleteDocs(BaseHandler):

    concurrency = 200
    max_runs = sys.maxint

    def iterunits(self):
#        logging.info("iterunits for deletedocs")
        owner = self.meta.kwargs.get('owner')
        domain = self.meta.domain
        nextLink=None
        retry = 0

        while True:
            try:
                feed, nextLink = docutils.get_users_docs(owner=owner, domain=domain, nextLink=None)
            except Exception, e:
                logging.error("Hit exception: %s" % e)
                retry += 1
                time.sleep(4 * retry)
                continue
            retry = 0
            for entry in feed.entry:
                yield entry.resource_id.text

            if not nextLink:
                logging.info("breaking out of iterunits")
                break

    def do_unit(self, unit):
        owner = self.meta.kwargs.get('owner')
        domain = self.meta.domain
        doc = docutils.get_doc(unit, owner, domain)
#        logging.info("title: %s owner: %s" % (doc.title.text, owner))
        #if doc.title.text == 'blank' or doc.title.text == 'blank.txt':
#        logging.info("deleting doc")
        docutils.delete_doc(owner, domain, unit, force=True, trash=True)
        #else:
        #    logging.info("not deleting doc")

    def op_done(self):
        # Update progress
        pass

