var set_wizard_buttons = function() {
  /* Get Wizard buttons, depending on context.
   *
   * The current wizard tab has a continuation if there are further tabs. The
   * wizard can be completed if there are no empty required fields. The buttons
   * in ``container`` will be shown or hidden depending on which are relevant.
   */
  var container = $('#wizard-buttons');
  var cont = container.find('#continue');
  var done = container.find('#finish');
  var or = container.find('div');
  var next_tab = $('.ui-tabs-selected').next();
  var inputs = $('.required ~ .field > :input');
  var names = {};

  cont.show();
  done.removeAttr('disabled');
  cont.removeAttr('disabled');
  or.show();

  if (!next_tab.length) {
    cont.attr('disabled', 'disabled');
  }

  var input = null;
  for (var i = 0; i < inputs.length; i++) {
    input = $(inputs[i]);
    var is_bad = (!input.val() ||
                  input.val() === 'none');
    if (is_bad) {
      // Multi-select can have another properly set
      if (!names[input.attr('name')]) {
        names[input.attr('name')] = false;
      }
    }
  }
  for (var k in names) {
    if (names[k] === false) {
      done.attr('disabled', 'disabled');
      //or.hide();
    }
  }
};


$(function() {
  // All checkboxes toggle
  $('.actionable th :checkbox').click(function(e) {
    var $this = $(this);
    var checkbox = $this.parents('table').find('tr td :checkbox.row-select');

    // Confirm selection of multiple pages
    if ($this.attr('checked')) {
      var paging = $('.pagination a').length > 0;
      if (paging) {
        var diag = $('#multi-confirm-dialog');
        $(diag).dialog({
          title: 'Select All?',
          resizable: false,
          height: 200,
          modal: true,
          buttons: {
            Yes: function() {
              $('#grid-select-all').val('yes');
              $(diag).dialog('close');
            },
            No: function() {
              $(diag).dialog('close');
            }
          }
        });
      }
      } else {
        $('#grid-select-all').val('');
      }
      checkbox.attr('checked', !checkbox.attr('checked'));
      checkbox.trigger('change');
    });

    // Disable checkbox-required buttons
    $('.disabling').each(function(e) {
      var $this = $(this);
      if ($this.is('button') || $this.is('input')) {
        $this.attr('disabled', 'disabled');
      }
      $this.addClass('disabled');
    });

    // Keep current disable/enable button state
    $('input[type=checkbox][name=vaults]').change(function(e) {
      if ($('input[type=checkbox][name=vaults]:checked').length === 0) {
        $('.disabling').attr('disabled', 'disabled');
        $('.disabling').addClass('disabled');
      } else {
        $('.disabling').attr('disabled', '');
        $('.disabling').removeClass('disabled');
      }
    });

    // Tabbed interface
    $('.tabbed-left').tabs().addClass('ui-tabs-vertical ui-helper-clearfix');
    $('.tabbed-left').removeClass('ui-widget ui-widget-content');
    $('.tabbed-left ul').removeClass('ui-widget-header');
    $('.tabbed-left li').removeClass('ui-corner-top').addClass('ui-corner-all');
    $('a.click-to-tab').click(function(e) {
            var tabname = this.href.toString().split("#")[1];
            $(".tabbed-left:first").tabs("select", tabname);
            e.preventDefault();
        });
    $('.tabbed-left').show();

    // Help tooltips
    $('.helptips .help').each(function(e) {
      var $this = $(this);
      var prev_input = $this.parent().prev('.field').children(':input');
      $this.qtip({
        prerender: true,
        content: {
          text: $this
        },
        position: {
          my: 'left center',
          at: 'right center',
          target: prev_input
        },
        show: {
          target: prev_input,
          event: 'click mouseenter focus'
        },
        hide: {
          target: prev_input,
          event: 'mouseleave blur'
        }
      });
    });

    // Highlight error'd tabs
    $('.errortabs .errorlist').each(function(e) {
      var $this = $(this);
      var parent = $this.parents('.tab');
      var tid = parent.attr('id').split('-');
      var link = $('a[href$=' + tid[1] + ']');
      var li = link.parent();
      li.addClass('errortab');
      if (!$this.data('goto')) {
        link.trigger('click');
        $this.data('goto', true);
      }
    });

    // Handle empty disabled fields (multi-vault edit)
    $('#wizard-form input[disabled]').each(function(e) {
        var $this = $(this);
        if (!$this.val()) {
            $this.val('<multi-vault edit>');
        }
    });

    // Disable buttons on submit
    $('#wizard-form').submit(function() {
        var img = $('<img src="/static/img/wait.gif">');
        $('#wizard-buttons').html(img);
        return true;
    });

    // Handle wizard buttons
    set_wizard_buttons();
    $('.ui-tabs-nav li a').click(set_wizard_buttons);
    $('.required ~ .field > :input').change(set_wizard_buttons);
    $('#continue').click(function() {
      var next_tab = $('.ui-tabs-selected').next();
      if (!next_tab.length) {
        next_tab = $('.ui-tabs-nav li:first');
      }
      next_tab.find('a').click();
      return false;
    });
  });
