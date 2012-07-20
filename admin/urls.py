from django.conf.urls.defaults import *

urlpatterns = patterns(
	    'admin.views',
	    url(r'^cheat/$', 'cheat', name="admin-cheat"),
)
