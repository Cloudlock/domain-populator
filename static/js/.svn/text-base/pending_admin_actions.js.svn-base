var pending_adminactions_update_url;
var container;

function adminactions_refresher_callback() {
    if(container.children().size()) {
        linkDialogs();  // from dialog.js; make dialog link in new html work
        window.setTimeout(adminactions_refresher, 15000);
    }
}

function adminactions_refresher() {
    container.load(pending_adminactions_update_url, 
                   adminactions_refresher_callback);
}

$(function() {
        pending_adminactions_update_url = $("#pending_adminactions_update_url").attr("href");
        container = $("#pending-admin-actions");
        adminactions_refresher();
    });
