import units
import random
import logging

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, NumSiteSetup
from gapps.usernames import user_list
from gapps.docnames import doclist
from gdocsaudit import sitesutils

class CreateSites(BaseHandler):

    concurrency = 1
    
    def prerun(self):
        domain = self.meta.domain
        numsitesetup = NumSiteSetup.get_by_key_name(domain)

        if not numsitesetup:
            numsitesetup = NumSiteSetup(key_name=domain)
            numsitesetup.put()

        #num_sites_to_make = 1
        percent = random.randint(1,100)

        if percent < numsitesetup.numsites300to125:
            #300 - 125
            num_sites_to_make = random.randint(125,300)
        elif percent < numsitesetup.numsites125to75:
            #125 - 75
            num_sites_to_make = random.randint(75,125)
        elif percent < numsitesetup.numsites75to25:
            # 75 - 25
            num_sites_to_make = random.randint(25,75)
        elif percent < numsitesetup.numsites25to10:
            # 25 - 10
            num_sites_to_make = random.randint(10,25)
        elif percent < numsitesetup.numsites10to5:
            # 10 - 5
            num_sites_to_make = random.randint(5,10)
        else:
            # 5 - 1
            num_sites_to_make = random.randint(1,5)

        self.meta.num_sites_to_make = num_sites_to_make


    def iterunits(self):
        for x in range(self.meta.num_sites_to_make):
            word1 = random.choice(doclist)
            word2 = random.choice(doclist)
            word3 = random.choice(doclist)

            yield '%s %s %s' % (word1, word2, word3)

    def do_unit(self, unit):
        owner = self.meta.kwargs.get('owner')
        domain = self.meta.domain


        new_site = sitesutils.create_site(owner, domain, unit)

        #run all the shares here or create yet another batch for that?


        if new_site:
            logging.info("Site created, now sharing")
            opargs = {
                'owner': owner,
                #'domain': domain,
                'site_id': new_site.id.text,
                #TODO started by will be a valid email eventually need to make sure not to add domain if already an email
                'email': self.meta.started_by,
            }
            #TODO go into share docs
            op = units.operation('populator.sharesites.ShareSites', domain=domain, opargs=opargs)
            op.start()
        else:
            logging.info("Site not created")


    def op_done(self):
        pass

