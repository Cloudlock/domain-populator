function getButtons(dialog) {
  /* Get the button set for some `dialog`. Should provide Cancel (to close)
     and Continue if a form exists.
  */
  var iframe_contents = $("iframe", dialog).contents();

  var cancel_caption_hint = iframe_contents.find(".button-hints .cancel-caption");
  var cancel_text;
  if (cancel_caption_hint.size()) {
      cancel_text = cancel_caption_hint.text();
  } else {
      cancel_text = "Cancel";
  }

  var buttons = [{
    text: cancel_text,
    click: function() { $(dialog).dialog("close"); }
  }];

  //var form = $("iframe", dialog).find("form");
  var form = iframe_contents.find("form");
  if (form.size()) {
    buttons.push({
      text: "Continue",
      click: function(e) {
                var container = $(e.currentTarget).parents('div');
                var loadingmsg = container.find('.loadingmsg');
                loadingmsg.show();
                container.find('iframe').contents().find('form').submit();
      }
    });
  }
  return buttons;
}

function linkDialogs() {
  /* Link up all the possible dialogs on the page. Links have the class
   * `dialog-link` and containers have the class `dialog-container` with IDs
   * of the form `link-<label>` and `container-<label>`, respectively. */

  $('.dialog-link').each(function() {
    var link = $(this);

    // make it so repeated calls to linkDialogs are OK
    if(link.data("linkDialogs-been-there")) {
        return;
    } else {
        link.data("linkDialogs-been-there", true);
    }

    var label = link.attr('id').split('-').slice(1).join('-');
    var cid = '#container-' + label;
    var container = $(cid);
    var height = container.attr('dialogHeight') || 400;
    var width = container.attr('x-width') || 600;
    link.click(function() {
            var subframe = container.children('iframe');
            var loadingmsg = $("<div class='loadingmsg' style='position:absolute;width:"+(width-50)+"px;padding-top:"+(Math.round(height*0.25))+"px;text-align:center;font-size:200%;'><img src='/static/img/loading_big.gif'/></div>");

            subframe.bind("load", function() {
                    container.dialog("option", "buttons", getButtons(container));
                    loadingmsg.hide();
                    subframe.show();
                });

            subframe.hide();
            loadingmsg.hide()
            container.prepend(loadingmsg);

            container.dialog({
                    autoOpen: true,
                        modal: true,
                        width: width,
                        height: height,
                        resizable: false,
                        buttons: getButtons(container),
                        beforeClose: function(event, ui) {
                          subframe.attr("src", "about:blank");
                          if(window.adminactions_refresher) {
                            adminactions_refresher();
                          }
                          loadingmsg.remove();
                        },
                        open: function(event, ui) {
                          loadingmsg.show();
                          subframe.attr("src", link.attr("href"));
                        }
                });
            // moved to dialog open event
            // subframe.attr("src", link.attr("href"));
            return false;
        });
      });
}

function confirmPopups() {
  /* Link elements with classes of `confirm` have confirmation dialogs attached
   * to them.
   */
  $('a.confirm').click(function(e) {
    var txt = $(this).attr('title');
    if (!txt) { txt = 'perform this action' }
    var diag = $('<div>Are you sure you wish to ' + txt + '?</div>')
    $('body').append(diag);
    $(diag).dialog({
      title: 'Confirm Action',
      resizable: false,
      height: 200,
      modal: true,
      buttons: {
        Confirm: function() {
          window.location = this.href;
        },
        Cancel: function() {
          $(diag).dialog('close');
          diag.remove();
        }
      }
    });
    return false;
  });
}

$(function() {
  linkDialogs();
  confirmPopups();
});

