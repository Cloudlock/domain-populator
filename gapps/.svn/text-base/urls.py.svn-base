from django.conf.urls.defaults import *

urlpatterns = patterns(
    'gapps.views',

    url(r'^support/$', 'domain_support', name="gapps-domain-support"),
    url(r'^deletion_policy/$', 'domain_deletion_policy', name="gapps-domain-deletion-policy"),
    url(r'oauth/$', 'domain_oauth', name="gapps-domain-oauth"),
    url(r'^(?P<domain>[^/]+)/$', 'index', name="gapps-index"),
    url(r'^(?P<domain>[^/]+)/setup/$', 'domain_setup', name="gapps-domain-setup"),
    url(r'^(?P<domain>[^/]+)/logout/$', 'logout', name="gapps-logout"),
    #url(r'^(?P<domain>[^/]+)/scan/$', 'domain_enqueue_page', name="gapps-domain-document-create"),
    url(r'^(?P<domain>[^/]+)/user/$', 'domain_user_crawl', name="gapps-domain-crawl-users"),
    url(r'^(?P<domain>[^/]+)/wizard/$', 'domain_wizard', name="gapps-domain-wizard"),
    url(r'^(?P<domain>[^/]+)/wizard_error/$', 'domain_wizard_learn_more', name="gapps-domain-wizard-learn-more"),
    url(r'^(?P<domain>[^/]+)/error/$', 'domain_status_error', name="gapps-domain-status-error"),
    url(r'^(?P<domain>[^/]+)/status/(?P<batch_id>\d+)/$', 'domain_status', name="gapps-domain-status"),
    #url(r'^(?P<domain>[^/]+)/maxuser/$', 'domain_enqueue_maxusers', name="gapps-domain-maxusers"),
    url(r'^(?P<domain>[^/]+)/createdocs/$', 'domain_create_docs', name="gapps-domain-create-docs"),
    url(r'^(?P<domain>[^/]+)/createusers/$', 'domain_create_users', name="gapps-domain-create-users"),
    url(r'^(?P<domain>[^/]+)/deletedocs/$', 'domain_delete_docs', name="gapps-domain-delete-docs"),
    url(r'^(?P<domain>[^/]+)/createsites/$', 'domain_create_sites', name="gapps-domain-create-sites"),
    url(r'^(?P<domain>[^/]+)/test/$', 'domain_test', name="gapps-domain-test"),
    url(r'^(?P<domain>[^/]+)/verify/$', 'domain_verify', name="gapps-domain-verify"),

    #url(r'^(?P<domain>[^/]+)/status/(?P<batch_id>\d+)/json/$', 'domain_status_json', name="gapps-domain-status-json"),
    url(r'^(?P<domain>[^/]+)/statusdocs/(?P<batch_id>[^/]+)/$', 'domain_status_create_docs', name="gapps-domain-status-create-docs"),
    url(r'^(?P<domain>[^/]+)/statususers/(?P<batch_id>[^/]+)/$', 'domain_status_create_users', name="gapps-domain-status-create-users"),
    url(r'^(?P<domain>[^/]+)/statusdelete/(?P<batch_id>[^/]+)/$', 'domain_status_delete_docs', name="gapps-domain-status-delete-docs"),

    url(r'^(?P<domain>[^/]+)/createlargeexposures/$', 'domain_create_large_exposures', name="gapps-domain-create-large-exposures"),



    url('^t/ulcrawl/(?P<domain>[^/]+)/$',
        'domain_enqueue_task_userlist', name="gapps-domain-user-task"),

) + patterns(

    'gapps.task_views',

#    url('^t/ucrawl/(?P<domain>[^/]+)/$',
#        'domain_user_scan', name="gapps-domain-user-crawl"),

#    url('^t/chunk_cleanup/(?P<domain>[^/]+)/$',
#        'domain_chunk_cleanup', name="gapps-domain-chunk-cleanup"),

#    url('^t/uchunk/$',
#        'domain_user_chunk', name="gapps-domain-user-chunk"),

#    url('^t/apicall/(?P<domain>[^/]+)/r/(?P<rept_id>\d+)/u/(?P<username>[^/]+)/$',
#        'apicall', name="gapps-domain-task-apicall"),

    url('^t/dcrawl/(?P<domain>[^/]+)/$',
        'domain_enqueue_task', name="gapps-domain-document-task"),



    url('^t/mucrawl/(?P<domain>[^/]+)/$',
        'domain_enqueue_task_maxusers', name="gapps-domain-maxusers-task"),

    url('^t/batch/start/(?P<batch_id>\d+)/$',
        'domain_batch_start', name="gapps-domain-task-batch-start"),

    url('^t/batch/chunk/(?P<chunk_id>\d+)/$',
        'domain_batch_chunk', name="gapps-domain-task-batch-chunk"),

) + patterns(
    'gapps.ajax',
    url(r'^(?P<domain>[^/]+)/ajax/wizard/$', 'domain_ajax_wizard_check', name="gapps-domain-wizard-error"),
)
