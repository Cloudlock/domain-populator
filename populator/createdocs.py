import units
import logging
import random

from google.appengine.ext import db

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, NumDocSetup, DocTypeSetup
from gapps.usernames import user_list
from gapps.docnames import doclist
from gdocsaudit import docutils, tools, sitesutils
#import batch.handlers
import populator

import gdata.docs.data


class CreateDocs(BaseHandler):

    concurrency = 1

    def prerun(self):
        kwargs = self.meta.kwargs
#        numdocsetup = NumDocSetup.get_by_key_name(self.meta.domain)
#        if not numdocsetup:
#            numdocsetup = NumDocSetup(key_name=self.meta.domain)
#            numdocsetup.put()

        #num_docs_to_make = 1
        percent = random.randint(1,100)

        if percent < 1: #numdocsetup.numdocs300to125:
            #300 - 125
            num_docs_to_make = random.randint(125,300)
        elif percent < 1: #numdocsetup.numdocs125to75:
            #125 - 75
            num_docs_to_make = random.randint(75,125)
        elif percent < 1: #numdocsetup.numdocs75to25:
            # 75 - 25
            num_docs_to_make = random.randint(25,75)
        elif percent < 23: #numdocsetup.numdocs25to10:
            # 25 - 10
            num_docs_to_make = random.randint(10,25)
        elif percent < 60: #numdocsetup.numdocs10to5:
            # 10 - 5
            num_docs_to_make = random.randint(5,10)
        else:
            # 5 - 0
            num_docs_to_make = random.randint(0,5)
#        num_docs_to_make = 1
        self.meta.num_docs_to_make = num_docs_to_make

        logging.info("Number of docs being made for owner: %s docs for %s" % (num_docs_to_make, kwargs.get('owner')))

#        if numdocsetup.doccount > numdocsetup.limit or numdocsetup.doccount > numdocsetup.userlimit:
#            logging.warning("Doc Limit hit - don't create any more docs")
#            #self.meta.num_docs_to_make = 0
#        else:
#            numdocsetup.doccount += self.meta.num_docs_to_make
#            numdocsetup.put()

#        logging.info("Number of documents to be created: %s" % self.meta.num_docs_to_make)

    def iterunits(self):
        for x in range(self.meta.num_docs_to_make):
            word1 = random.choice(doclist)
            word2 = random.choice(doclist)
            word3 = random.choice(doclist)

            yield '%s %s %s' % (word1, word2, word3)


    def do_unit(self, unit):
        owner = self.meta.kwargs.get('owner')
        logging.info(owner)
        domain = self.meta.domain
        logging.info(domain)
        title = unit
        logging.info(title)
        batch_id = self.meta.key().id()
        logging.info(batch_id)

#        doctypesetup = DocTypeSetup.get_by_key_name(domain)

#        if not doctypesetup:
#            doctypesetup = DocTypeSetup(key_name=domain)
#            doctypesetup.put()

        percent = random.randint(1,100)
        if percent < 53: #doctypesetup.docratio:
            #Doc
            doc_type = gdata.docs.data.DOCUMENT_LABEL
        elif percent < 85: #doctypesetup.spreadratio:
            # Spreadsheet
            doc_type = gdata.docs.data.SPREADSHEET_LABEL
        elif percent < 88: #doctypesetup.presratio:
            # Presentation
            doc_type = gdata.docs.data.PRESENTATION_LABEL
        elif percent < 95: #doctypesetup.pdfratio:
            # pdf
            doc_type = 'pdf'
        else:
            # folder
            doc_type = gdata.docs.data.FOLDER_LABEL

        if doc_type == 'pdf':
            new_doc = docutils.create_pdf(owner, domain, title, batch_id)
        elif doc_type == gdata.docs.data.FOLDER_LABEL:
            new_doc = docutils.create_folder(owner, domain, title,doc_type)
            if new_doc:
                memcache.set('folder_id:%s' % batch_id, new_doc.resource_id.text)
                memcache.set('folder_limit:%s' % batch_id, random.randint(1,5))
        else:
            new_doc = docutils.create_empty_doc(owner,domain, title, batch_id, doc_type)

        #TODO what do you do if it's a folder

        #run all the shares here or create yet another batch for that?

#        numdocsetup = NumDocSetup.get_by_key_name(self.meta.domain)
        #TODO might need to create new tasks just to share domain and public and outside domain

        if new_doc:
            logging.info("Document created, now sharing")
            #TODO I think this is what I want to be doing (to create an accurate count? maybe?)
#            def txn_add():
#                numdocsetup.progress_doccount += 1
#                numdocsetup.put()
#            db.run_in_transaction(txn_add)

            opargs = {
                'owner': owner,
                #'domain': domain,
                'doc_id': new_doc.resource_id.text,
                #TODO started by will be a valid email eventually need to make sure not to add domain if already an email
                'email': self.meta.started_by,
            }
            #TODO go into share docs
            op = units.operation('populator.sharedocs.ShareDocs', domain=domain, opargs=opargs)
            op.start()
        else:
            logging.info("Document not created")
#            def txn_fail():
#                numdocsetup.doccount -= 1
#                numdocsetup.put()
#            db.run_in_transaction(txn_fail)




    def op_done(self):
        #TODO restart create docs if we haven't hit the limit yet
        pass


