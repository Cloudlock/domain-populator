import units
import random
import logging


from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup, ShareSetup, TrackingValues, ReportingValues
from gapps.usernames import user_list
from gdocsaudit import docutils, tools, sitesutils
from google.appengine.api import mail, memcache
from google.appengine.ext import db

from gdata.client import RequestError

class ModifyDocs(BaseHandler):
    
    concurrency = 50
    other_share_list = []
    


    def prerun(self):
        kwargs = self.meta.kwargs
        
        pass


    def iterunits(self):
        owner = self.meta.kwargs.get('owner')
        doc_list = docutils.get_docs(owner, self.meta.domain, categories=['mine'])
        for doc in doc_list:
            yield doc.resource_id.text


    def do_unit(self, unit):
        logging.info("Got into do_unit for modifydocs")
        def _update_reporting_values_trans(update_list, doc_id, domain):
            key = domain + ':reporting'
            rv = ReportingValues.get_by_key_name(key)
            for value_to_update in update_list:
                logging.info("value_to_update %s", value_to_update)
                if value_to_update == 'modifyacl':
                    rv.modifyacl.append(doc_id)
                if value_to_update == 'removepublic':
                    rv.removepublic.append(doc_id)
                if value_to_update == 'removeinternal':
                    rv.removeinternal.append(doc_id)
                if value_to_update == 'removeexternaluser':
                    rv.removeexternaluser.append(doc_id)
                if value_to_update == 'addpublic':
                    rv.addpublic.append(doc_id)
                if value_to_update == 'addinternal':
                    rv.addinternal.append(doc_id)
                if value_to_update == 'addexternaluser':
                    rv.addexternaluser.append(doc_id)
                if value_to_update == 'changecontent':
                    rv.changecontent.append(doc_id)
                if value_to_update == 'changetitle':
                    rv.changetitle.append(doc_id)
                if value_to_update == 'addinternaluser':
                    rv.addinternaluser.append(doc_id)
                if value_to_update == 'removeinternaluser':
                    rv.removeinternaluser.append(doc_id)
                if value_to_update == 'changeowner':
                    rv.changeowner.append(doc_id)
                if value_to_update == 'deletedoc':
                    rv.deletedoc.append(doc_id)
                if value_to_update == 'createdoc':
                    rv.createdoc.append(doc_id)
            rv.put()
	
        def _update_tracking_values_trans(domain):
            update_list = []
            key = domain + ':tracking'
            tv = TrackingValues.get_by_key_name(key)
            sum = (tv.removepublic +
                   tv.removeinternal + 
                   tv.deletedoc + 
                   tv.removeinternaluser + 
                   tv.removeexternaluser +
                   tv.addinternaluser + 
                   tv.addexternaluser +
                   tv.addpublic +
                   tv.addinternal +
                   tv.changeowner +
                   tv.modifyacl)
            if sum == 0:
                return update_list



            if tv.removepublic > 0 and doc_acl.find(scope_type='default'):
                update_list.append('removepublic')
                tv.removepublic -= 1
                logging.info("tv.removepublic %s", tv.removepublic)
            elif tv.removeinternal > 0 and doc_acl.find(scope_type='domain'):
                update_list.append('removeinternal')
                tv.removeinternal -= 1
                logging.info("tv.removeinternal %s", tv.removeinternal)
            elif tv.deletedoc > 0:
                update_list.append('deletedoc')
                tv.deletedoc -= 1
                logging.info("tv.deletedoc %s", tv.deletedoc)
            else:
                acls = doc_acl.find(scope_type='user')
                for acl in acls:
                    if acl.role.value == 'owner':
                        continue
                    (user, user_domain) = acl.scope.value.split('@')
                    if user_domain == domain:
                        if tv.removeinternaluser > 0:
                            update_list.append('removeinternaluser')
                            tv.removeinternaluser -= 1
                            logging.info("tv.removeinternaluser %s", tv.removeinternaluser)
                    else:
                        if tv.removeexternaluser > 0:
                            update_list.append('removeexternaluser')
                            tv.removeexternaluser -= 1
                            logging.info("tv.removeexternaluser %s", tv.removeexternaluser)
        	
                if tv.addinternaluser > 0:
                    update_list.append('addinternaluser')
                    tv.addinternaluser -= 1
                    logging.info("tv.addinternaluser %s", tv.addinternaluser)
                    
                if tv.addexternaluser > 0:
                    # Get external user from kwargs and then add them only if the user doesn't already have access
                    update_list.append('addexternaluser')
                    tv.addexternaluser -= 1
                    logging.info("tv.addexternaluser %s", tv.addexternaluser)
        	
                if tv.addpublic > 0 and not doc_acl.find(scope_type='default'):
                    update_list.append('addpublic')
                    tv.addpublic -= 1
                    logging.info("tv.addpublic %s", tv.addpublic)
                elif tv.addinternal > 0 and not doc_acl.find(scope_type='domain'):
                    update_list.append('addinternal')
                    tv.addinternal -= 1
                    logging.info("tv.addinternal %s", tv.addinternal)
                if tv.changeowner > 0 and owner != self.meta.kwargs.get('change_owner_to'):
                    update_list.append('changeowner')
                    tv.changeowner -= 1
                    logging.info("tv.changeowner %s", tv.changeowner)
                if tv.modifyacl > 0 and not update_list and doc_acl.find(scope_type='user'):
                    update_list.append('modifyacl')
                    tv.modifyacl -= 1
                    logging.info("tv.modifyacl %s", tv.modifyacl)

            tv.put()
            return update_list
	
        owner = self.meta.kwargs.get('owner')
        domain = self.meta.domain
        doc_id = unit
        doc_acl = docutils.get_doc_acl(owner, domain, doc_id)

        #scope type = user, domain, default
        #role = writer, reader, owner
        
        #Get doc acl
        #Get ACL change memcache values
        #Check acl against memcache values

        key = domain + ':tracking'
        tv = TrackingValues.get_by_key_name(key)
        update_list = []

        update_list = db.run_in_transaction(_update_tracking_values_trans, domain)
        
        if not update_list:
            return

        if 'removepublic' in update_list:
            docutils.mod_acl(owner, domain, doc_id, scope_value=None, scope_type='default', role=None, force_post=True)
        elif 'removeinternal' in update_list:
            docutils.mod_acl(owner, domain, doc_id, scope_value=domain, scope_type='domain', role=None, force_post=True)
        elif 'deletedoc' in update_list:
            docutils.delete_doc(owner, domain, doc_id, force=True)
        else:
            acls = doc_acl.find(scope_type='user')
            for acl in acls:
                if acl.role.value == 'owner':
                    continue
                (user, user_domain) = acl.scope.value.split('@')
                if user_domain == domain:
                    if 'removeinternaluser' in update_list:
                        docutils.mod_acl(owner, domain, doc_id, scope_value=acl.scope.value, role=None, force_post=True)
                        break
                else:
                    if 'removeexternaluser' in update_list:
                        docutils.mod_acl(owner, domain, doc_id, scope_value=acl.scope.value, role=None, force_post=True)
                        break
            if 'addinternaluser' in update_list:
                try:
                    username = memcache.get(domain + ":username:modify")
                    if username is None:
                        logging.info("Something happened and need to reset the memcache")
                        username = DomainUser.all().filter('domain =', domain).get().username
        	
                    try:
                        domain_user = DomainUser.all().filter('domain =', domain).filter('username >', username).get().username
                        if domain_user == owner or domain_user in [acl.scope.value for acl in acls]:
                            domain_user = DomainUser.all().filter('domain =', domain).filter('username >', domain_user).get().username
                    except:
                        logging.info("Reached end of user list, starting over.")
                        domain_user = DomainUser.all().filter('domain =', domain).get().username
        	
        	
                    success = memcache.set(domain + ":username:modify", domain_user)
                    if success:
                        logging.info("Successful memcache set")
                    else:
                        logging.info("Unsuccessful memcache set")
        	
                    #TODO add share here
                    docutils.share_user(owner, domain, doc_id, '@'.join((domain_user,domain)))
                except RequestError, e:
                    logging.warn(e.args)
                    if "emails could not be sent" in getattr(e,'body',''):
                        # We experienced a case when the ownership was changed but google failed to send the notification email to
                        # the new owner. We don't need to consider this case as a failure
                        pass
                    else:
                        raise
            if 'addexternaluser' in update_list:
                # Get external user from kwargs and then add them only if the user doesn't already have access
                docutils.share_user(owner, domain, doc_id, self.meta.kwargs.get('external_user'))
        	
            if 'addpublic' in update_list:
                docutils.share_public(owner, domain, doc_id)
            if 'addinternal' in update_list:
                docutils.share_domain(owner, domain, doc_id)
        	
            if 'changeowner' in update_list:
                docutils.change_owner(owner, self.meta.kwargs.get('change_owner_to'), domain, doc_id)
        	
            if 'modifyacl' in update_list:
                logging.info('modifyacl in update_list')
                from admin.debug import dbg;dbg()

                rolecount = random.randint(0,1)
                if rolecount == 0:
                    role = 'reader'
                    role_change = 'writer'
                else:
                    role = 'writer'
                    role_change = 'reader'
        	
                acls = doc_acl.find(role=role, scope_type='user')
                if not acls:
                    # if the desired role change is not there then switch
                    acls = doc_acl.find(role=role_change, scope_type='user')
                    role_change = role
                acl = acls[0]
                try:
                    docutils.mod_acl(owner, domain, doc_id, scope_value=acl.scope.value, role=role_change, force_post=True)
                except:
                    logging.info("Exception")
                logging.info('mod_acl called')

        if update_list:
            db.run_in_transaction(_update_reporting_values_trans, update_list, doc_id, domain)

        return


    def op_done(self):
        # Set progress and send email if necessary
        # Check if some numbers are still > 0 and repeat if necessary
        pass



