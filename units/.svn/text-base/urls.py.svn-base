from django.conf.urls.defaults import patterns, url


# Task views
urlpatterns = patterns('units.tasks',
    url(r'run/(?P<oid>\d+)$', 'run', name='task-run'),
    url(r'active/(?P<oid>\d+)/$', 'active', name='task-active'),
    url(r'sync/(?P<oid>\d+)/$', 'sync', name='task-sync'),
    url(r'finish/op/(?P<oid>\d+)/$', 'finish_op', name='task-finish-op'),
    url(r'finish/group/(?P<oid>\d+)/$', 'finish_group', name='task-finish-group'),
)

# Other views
urlpatterns += patterns('units.views',
    url(r'xhr/totals/$', 'xhr_totals', name='xhr-totals'),
)
