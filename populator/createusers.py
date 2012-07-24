import units

from units.handlers import BaseHandler
from units.models import OperationMeta
from gapps.models import DomainUser, DomainSetup
from gapps.usernames import user_list

class CreateUsers(BaseHandler):

    concurrency = 1

    def iterunits(self):
        ds = DomainSetup.get_for_domain(self.meta.domain)
        lower_index = ds.owner_offset
        higher_index = lower_index + self.meta.kwargs.get('num_users_to_create')
        ds.owner_offset = higher_index
        ds.put()
        for index in range(lower_index, higher_index):
            yield user_list[index]
            

    def do_unit(self, unit):

        INIT = {
        'APP_NAME': settings.API_CLIENT_SOURCE,
        'SCOPES': ['https://apps-apis.google.com/a/feeds/']
        }

        domain = self.meta.domain

        service = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE, domain=domain)

        sh = ServiceHelper.get_by_key_name(domain)

        if sh.access_token is not None:
            access_token = pickle.loads(sh.access_token)
            service.token_store.add_token(access_token)
            service.current_token = access_token
            service.SetOAuthToken(access_token)
            logging.info("access_token: %s" % access_token)

        ds = DomainSetup.get_for_domain(domain)
        if ds.user_created_count > ds.user_limit:
            return


        if True:

            names = unit.split('.')
            user_name = unit
            family_name = names[1]
            given_name = names[0]
            password = "cl0udl0ck"
            new_user = None
            try:

                new_user = service.CreateUser(user_name, family_name, given_name, password, suspended='false', quota_limit=gdata.apps.service.DEFAULT_QUOTA_LIMIT,password_hash_function=None)

            except gdata.apps.service.AppsForYourDomainException, e:
                #if entity exists break {'status': 400, 'body': '<?xml version="1.0" encoding="UTF-8"?>\r\n<AppsForYourDomainErrors>\r\n  <error errorCode="1300" invalidInput="JOHN.WILLIAMS" reason="EntityExists" />\r\n</AppsForYourDomainErrors>\r\n\r\n', 'reason': 'Bad Request'}
                logging.warn(e.args)
                if e.reason == "EntityExists":
                    logging.warn("User already exists")
                    #make sure we cover the odd case where a user already exists
                    #if we don't have a domain user value create it and take credit for creating it
                    #TODO might not be the best choice fix this later
                    key_name = DomainUser.make_key_name(domain, unit)
                    duser = DomainUser.get_by_key_name(key_name)
                    if duser is None:
                        duser = DomainUser(key_name=key_name, username=unit, domain=domain, created_by_us=True)
                        duser.put()

                        logging.info("DomainUser Value Created: %s" % unit)
                    else:
                        #Make sure duser is considered created by us
                        duser.created_by_us = True
                        duser.put()
                        logging.info("DomainUser Already Exists: %s" % unit)
                    pass
                else:
                    raise
            if new_user:
                logging.info("New User is: %s", new_user.login.user_name)

                ds.user_created_count += 1
                ds.put()

                """Returns created/updated DomainUser object"""
                key_name = DomainUser.make_key_name(domain, unit)
                duser = DomainUser.get_by_key_name(key_name)
                if duser is None:
                    duser = DomainUser(key_name=key_name, username=unit, domain=domain, created_by_us=True)
                    duser.put()

                    logging.info("DomainUser Value Created: %s" % unit)
                else:
                    #Make sure duser is considered created by us
                    duser.created_by_us = True
                    duser.put()
                    logging.info("DomainUser Already Exists: %s" % unit)
            else:
                logging.warn("New User not created")
        else:
            logging.warn("New User not created")

        #TODO show progress here


    def op_done(self):
        #TODO update progress
        #TODO run get users with correct scope
        pass



