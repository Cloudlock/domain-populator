import units
import logging
import random

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, ShareSetup
from gapps.usernames import user_list
from gdocsaudit import docutils, tools, sitesutils

from google.appengine.api import mail, memcache

from gdata.client import RequestError

class ShareSites(BaseHandler):

    concurrency = 1
    other_share_list = []

    def prerun(self):
        kwargs = self.meta.kwargs
        #num_sites_to_make = 1

        self.meta.other_share_list = []

        sharesetup = ShareSetup.get_by_key_name(self.meta.domain)

        if not sharesetup:
            sharesetup = ShareSetup(key_name=self.meta.domain)
            sharesetup.put()


        #TODO Get number of users in domain and make sure not to go over that
        
        percent = random.randint(1,100)

        if percent < sharesetup.shares20to22:
            #20-22
            self.meta.num_shares = random.randint(20,22)
        elif percent < sharesetup.shares15to20:
            # 15-20
            self.meta.num_shares = random.randint(15,20)
        elif percent < sharesetup.shares10to15:
            # 10-15
            self.meta.num_shares = random.randint(10,15)
        elif percent < sharesetup.shares5to10:
            # 5-10
            self.meta.num_shares = random.randint(5,10)
        elif percent < sharesetup.shares3to5:
            # 3-5
            self.meta.num_shares = random.randint(3,5)
        elif percent < sharesetup.shares1to3:
            # 1-3
            self.meta.num_shares = random.randint(1,3)
        else:
            # 0
            self.meta.num_shares = 0

        #self.meta.num_shares = 1

        #Try sharing with public or domain, and outside users
        othershares = random.randint(1,100) + 1

        if othershares < sharesetup.sharespublic:
            #docutils.share_public(owner,domain,new_doc.resource_id.text)
            #share with public
            self.meta.other_share_list.append('public')
        elif othershares < sharesetup.sharesdomain:
            #docutils.share_domain(owner,domain,new_doc.resource_id.text)
            #share with domain
            self.meta.other_share_list.append('domain')

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside1:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'admin@uitribe.com')
            #share with uitribe
            self.meta.other_share_list.append(sharesetup.outsideuser1)

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside2:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'aprigoqagdocs@gmail.com')
            #share with aprigoqagdocs
            self.meta.other_share_list.append(sharesetup.outsideuser2)

        logging.info("Number of shares for site: %s internal %s external" % (self.meta.num_shares, len(self.meta.other_share_list)))


    def iterunits(self):
        # TODO don't need to get domain setup every time
        ds = DomainSetup.get_for_domain(self.meta.domain)
        ds_users = int(ds.num_users)
        if self.meta.num_shares >= ds_users and ds_users != 0:
            self.meta.num_shares = ds_users - 1
        count = self.meta.num_shares + len(self.meta.other_share_list)
        shares = [str(i) for i in range(self.meta.num_shares)]
        shares = shares + self.meta.other_share_list

        for unit in shares:
            yield unit


    def do_unit(self, unit):
        owner = self.meta.kwargs.get('owner')
        site_id = self.meta.kwargs.get('site_id')
        domain = self.meta.domain

        sharesetup = ShareSetup.get_by_key_name(domain)
        try:
            if unit == 'domain':
                sitesutils.share_domain(owner,domain,site_id)
            elif unit == 'public':
                sitesutils.share_public(owner,domain,site_id)
            elif unit == sharesetup.outsideuser1:
                sitesutils.share_user(owner,domain,site_id,sharesetup.outsideuser1)
            elif unit == sharesetup.outsideuser2:
                sitesutils.share_user(owner,domain,site_id,sharesetup.outsideuser2)
            else:
                username = memcache.get("username")
                if username is None:
                    logging.info("Something happened and need to reset the memcache")
                    username = DomainUser.all().filter('domain =', domain).get().username

                try:
                    domain_user = DomainUser.all().filter('domain =', domain).filter('username >', username).get().username
                    if domain_user == owner:
                        domain_user = DomainUser.all().filter('domain =', domain).filter('username >', domain_user).get().username
                except:
                    logging.info("Reached end of user list, starting over.")
                    domain_user = DomainUser.all().filter('domain =', domain).get().username


                success = memcache.set("username", domain_user)
                if success:
                    logging.info("Successful memcache set")
                else:
                    logging.info("Unsuccessful memcache set")

                #TODO add share here
                sitesutils.share_user(owner, domain, site_id, '@'.join((domain_user,domain)))
        except RequestError, e:
            logging.warn(e.args)
            if e.status == 409 and "user already has access to the site" in getattr(e, 'body', ''):
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



