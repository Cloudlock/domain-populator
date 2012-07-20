from django.core.management.base import BaseCommand
from django.conf import settings
from django import template
import django.template.loader
import sys

class Command(BaseCommand):
    def handle(self, *args, **kwargs_dummy):
        if len(args) != 0:
            print "The gen_manifest command takes no input."
            sys.exit(1)

        t = template.loader.get_template("marketplace/manifest.xml")

        manifest_text = t.render(template.Context({
                    "baseurl": "%s/ga/" % settings.DEPLOYED_URL,
                    "openID_realm": settings.OPENID_REALM,
                    }))

        print manifest_text
