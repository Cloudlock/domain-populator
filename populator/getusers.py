import units
import logging
import sys

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, TrackingValues, ReportingValues
from gapps.usernames import user_list
from gdocsaudit import docutils, tools, sitesutils

class GetUsers(BaseHandler):

    concurrency = 1
    max_runs = sys.maxint

    def prerun(self):
        logging.info("Got into prerun")
        action = self.meta.kwargs.get('action')
        domain = self.meta.domain
        if action == 'modifydocs':
            # TODO make these values based on opargs
	    key = domain + ':tracking'
	    tv = TrackingValues(key_name=key, 
	                        modifyacl=25, 
	                        removepublic=1,
	                        removeinternal=1,
	                        removeexternaluser=1,
	                        addpublic=1,
	                        addinternal=1,
	                        addexternaluser=1,
	                        changecontent=1,
	                        changetitle=1,
	                        addinternaluser=1,
	                        removeinternaluser=1,
	                        changeowner=1,
	                        deletedoc=1,
	                        createdoc=1)
	
	    tv.put()
	    key = domain + ':reporting'
	    rv = ReportingValues(key_name=key, 
                                 modifyacl=[], 
                                 removepublic=[],
                                 removeinternal=[],
                                 removeexternaluser=[],
                                 addpublic=[],
                                 addinternal=[],
                                 addexternaluser=[],
                                 changecontent=[],
                                 changetitle=[],
                                 addinternaluser=[],
                                 removeinternaluser=[],
                                 changeowner=[],
                                 deletedoc=[],
                                 createdoc=[])
	    rv.put()


    def iterunits(self):
        #TODO do this differently 
        nextLink=self.meta.kwargs.get('nextLink', None)
#        count = self.meta.kwargs.get('count', 0)
#        logging.info("count is at %s", count)
        logging.info('at the top of iterunits, nextlink is %s', nextLink)
        while True:
#            count = count + 1
#            self.meta.set_op_arg('count', count)

            client = tools.get_gapps_client(self.meta.kwargs.get('started_by'), self.meta.domain, svc="prov")

            users_list, limit_remaining, nextLink = tools.get_some_users(client=client, usernames_only=False, limit=None, next_link=nextLink)

            logging.info('got here 1')
            for u in users_list:
                logging.info("username: %s" % u.title.text)#u.username.text)
                yield u.title.text

            if not nextLink:
                break
            else:
                self.meta.set_op_arg('nextLink', nextLink)
            #    nextLink = nextLink.href


    def do_unit(self, unit):
        """Returns created/updated DomainUser object, or None if we should skip it."""
        domain = self.meta.domain
        scope = self.meta.kwargs.get('scope')
        action = self.meta.kwargs.get('action')
        key_name = DomainUser.make_key_name(domain, unit)
        duser = DomainUser.get_by_key_name(key_name)
        if duser is None:
            duser = DomainUser(key_name=key_name, username=unit, domain=domain)
            duser.put()

            logging.info("DomainUser Value Created: %s" % unit)
#        else:
#            logging.info("DomainUser Already Exists: %s" % unit)
#        logging.info("Get Users action: " + action)
        if action == "createdocs":
            if scope == "all" or (scope == "created" and duser.created_by_us):
                logging.info("Starting new batch op for creating docs")
                opargs = {
                    'owner': unit,
                    }
                op = units.operation('populator.createdocs.CreateDocs', domain=domain, opargs=opargs)
                op.start()

        elif action == "deletedocs":
#            logging.info("Starting new batch op for delete docs")
            opargs = {
                'owner': unit,
                }
            op = units.operation('populator.deletedocs.DeleteDocs', domain=domain, opargs=opargs)
            op.start()
        elif action == "createsites":
            logging.info("Starting new batch op for create sites")
            opargs = {
                'owner': unit,
                }
            op = units.operation('populator.createsites.CreateSites', domain=domain, opargs=opargs)
            op.start()

        elif action == "modifydocs":
            # TODO make external_user and change_owner_to based on opargs
	    opargs = {
	        'owner': unit,
	        'external_user': 'john.smith@externaluser1.com',
	        'change_owner_to': 'tull@everyoneexposure.com',
	        }
	    op = units.operation('populator.modifydocs.ModifyDocs', domain=domain, opargs=opargs)
	    op.start()



    def op_done(self):
        #Show progress - status
        pass
