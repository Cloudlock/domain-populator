from django.conf.urls.defaults import patterns, url


urlpatterns = patterns('status.views',
    url(r'finished/$', 'finished', name='status-finished'),
    url(r'operations/$', 'operations', name='status-operations'),
    url(r'test/$', 'test', name='status-test'),
    url(r'test/send/$', 'test_send', name='status-test-send'),
    url(r'test/op/$', 'test_op', name='status-test-op'),
    url(r'token/$', 'token', name='status-token'),
    url(r'token/clear/$', 'token', { 'clear': True },
        name='status-token-clear'),
    url(r'missing/$', 'missing', name='status-missing'),
)

