/*global goog: false, log: true*/

/*
 * jQuery doTimeout: Like setTimeout, but better! - v1.0 - 3/3/2010
 * http://benalman.com/projects/jquery-dotimeout-plugin/
 * 
 * Copyright (c) 2010 "Cowboy" Ben Alman
 * Dual licensed under the MIT and GPL licenses.
 * http://benalman.com/about/license/
 */
(function($){var a={},c="doTimeout",d=Array.prototype.slice;$[c]=function(){return b.apply(window,[0].concat(d.call(arguments)))};$.fn[c]=function(){var f=d.call(arguments),e=b.apply(this,[c+f[0]].concat(f));return typeof f[0]==="number"||typeof f[1]==="number"?this:e};function b(l){var m=this,h,k={},g=l?$.fn:$,n=arguments,i=4,f=n[1],j=n[2],p=n[3];if(typeof f!=="string"){i--;f=l=0;j=n[1];p=n[2]}if(l){h=m.eq(0);h.data(l,k=h.data(l)||{})}else{if(f){k=a[f]||(a[f]={})}}k.id&&clearTimeout(k.id);delete k.id;function e(){if(l){h.removeData(l)}else{if(f){delete a[f]}}}function o(){k.id=setTimeout(function(){k.fn()},j)}if(p){k.fn=function(q){if(typeof p==="string"){p=g[p]}p.apply(m,d.call(n,i))===true&&!q?o():e()};o()}else{if(k.fn){j===undefined?e():k.fn(j===false);return true}else{e()}}}})(jQuery);


var log = window.console ? console.log : function() {};


function jq(myid) { 
   return '#' + myid.replace(/(:|\.)/g,'\\$1');
 }


function getParameterByName(name) {
  var match = RegExp('[?&]' + name + '=([^&]*)')
                  .exec(window.location.search);
  return match && decodeURIComponent(match[1].replace(/\+/g, ' '));
}


var handlerInit = {
  init: true,
  autoClose: false,
  currentStep: null,
  completed: false,
  finished: false,
  // Tracked for incr
  total: 0,
  currentTotal: 0,
  currentProgress: 0,
  currentArgs: {},
  dialogOpts: {
    modal: false,
    closeOnEscape: false,
    resizable: false,
    draggable: false
  },
  steps: [],
  doneTmpl: $('#status-done-tmpl'),
  totalsPending: false
};


var handlerMethods = {
  elm: function() {
    return $(jq(this.id));
  },

  hasUI: function() {
    return this.elm().find('.bar-container').length !== 0;
  },

  trigger: function(name) {
  /**
   * Wrapper around jQuery's trigger.
   *
   * Namespace to `status`, insert `this` as first argument and call on
   * `this.container`.
   */
    var args = [].splice.call(arguments, 0);
    args.splice(1, 0, this);
    var final = [args[0]+'.status', args.splice(1)];
    $(this).trigger.apply(this.elm(), final);
  },

  removeUI: function() {
  /**
   * Remove an Operation's UI (progress bar, etc.) from the DOM.
   *
   * Fires `postremoveui.status` if successful.
   *
   */
    var container = this.elm();
    container.hide();
    container.empty();
    var dialog = container.data('dialog');
    if (dialog) {
      dialog.remove();
      container.data('dialog', null);
    }
    this.trigger('postremoveui');
  },

  addStep: function(name, tmpl) {
  /**
   * Add a step to the Operation.
   *
   * @param name string Named step; used to reference template.
   * @param tmpl mixed A jQuery selector for the template in the DOM; string
   *   template; etc.
   *
   */
    $.template(name, tmpl);
    this.steps.push(name);
    if (this.currentStep === null) {
      this.currentStep = 0;
    }
  },

  buildUI: function(conf) {
  /**
   * Configure the display of the given operation handler.
   *
   * Fires `postbuildui.status` if successful.
   *
   * @param conf object A configuration object.
   *
   */
    this.trigger('prebuildui', conf);
    conf = conf || {};
    this.removeUI();

    container = this.elm();
    container.show();
    // Progress bar element
    if (conf.bar === undefined || conf.bar.length === 0) {
      bar = $('<div class="bar-container"></div>');
      container.append(bar);
    } else {
      bar = conf.bar;
    }
    container.data('bar', bar);
    bar.progressbar();
    // Pre-progress message in bar
    if (this.tracker.settings.prepEl) {
      bar.append(this.tracker.settings.prepEl.clone());
    }
    // Label
    label = null;
    if (conf.label) {
      label = $('<span class="op-label">' + conf.label + '</span>');
      bar.before(label);
    }
    // Setup dialog
    dialog = false;
    if (conf.dialog === true) {
      var diag = $('<div class="status-dialog"></div>');
      diag.dialog(this.dialogOpts);
      container.data('dialog', diag);
      dialog = diag;
    } else if (typeof(conf.dialog) === 'object') {
      conf.dialog.elm.dialog(
        $.extend(this.dialogOpts, conf.dialog)
      );
      container.data('dialog', conf.dialog.elm);
      dialog = conf.dialog.elm;
    }
    if (dialog !== false) {
      if (label) {
        dialog.dialog('option', 'title', conf.label);
        label.remove();
      }
      dialog.append(container);
    }

    this.trigger('postbuildui', conf);
  },

  getProgress: function(val, incr) {
  /**
   * Extract a progress percentage from a data object.
   *
   * @param val intger The update message's "val" (1, 2, etc.)
   * @param incr bool The update message's "incr" (true || false)
   * @return integer percentage complete.
   */
    var pct = null;
    var num = parseInt(val, 10);
    if (this.total === 0) {
      this.getTotals();
      return 0;
    }
    if (incr) {
      this.currentTotal += num;
    } else {
      this.currentTotal = num;
    }
    pct = Math.round((this.currentTotal / this.total) * 100);
    return pct;
  },

  progress: function(pct, notrigger) {
  /**
   * Increment this handler's progress bar.
   *
   * Fires `changed.status` for pct != 100; `complete.status` otherwise.
   *
   * @param pct integer A number (0-100) indicating percentage done.
   */
    var isComplete = pct >= 100;
    bar = this.bar;
    if (bar === undefined) {
      throw "Called progress() on non-built handler";
    }

    if (pct > 0) {
      bar.find('.prep').hide();
    } else {
      bar.find('.prep').hide();
    }

    bar.progressbar({ 'value': pct });
    if (notrigger === undefined && isComplete !== true) {
      this.trigger('change', pct);
    }

    if (pct % 10 === 0) {
        $.doTimeout('completeTotal', 5000,
                    $.proxy(this.getTotals, this));
    }

    if (isComplete) {
      if (this.completed !== true) {
        this.completed = true;
        this.trigger('complete');
      }
      this.finish();
    }
  },

  finish: function() {
  /**
   * Finish an Operation.
   *
   * This method only works if `resume_url` or `finished_on` are present, and
   * if the handler isn't set to `autoClose`.
   *
   * Fires `finished.status` if successful.
   *
   */
    if (!this.resume_url && !this.finished_on && this.autoClose) {
      this.tracker.forget(this);
    } else if ((this.resume_url || this.finished_on) && !this.finished) {
      this.trigger('finished');
      this.finished = true;
      var rendered = $.tmpl(this.doneTmpl, this);
      var body = this.elm().find('.body');
      if (body.length === 0) {
        body = $('<span class="body"></span>');
        this.elm().append(body);
      }
      body.html(rendered);
    }
  },

  message: function(opData) {
  /**
   * A message has been received.
   *
   * See Data Specification documentation for more info.
   *
   * Fires `message`
   *
   */
    this.trigger('message', opData);

    // We may receive messages out of order; don't un-finish a complete
    // operation due to lazy messages. We may want to update an existing
    // one with url or finish time, though.
    if (this.completed && (!opData.resume_url &&
                           !opData.finished_on &&
                           !opData.total)) {
      return;
    }

    var has_resume = Boolean(this.resume_url);
    var has_finished = Boolean(this.finished_on);

    // Update resume_url
    if (opData.resume_url !== undefined) {
      this.resume_url = opData.resume_url;
    }
    // Update finished_on
    if (opData.finished_on !== undefined) {
      this.finished_on = opData.finished_on;
    }
    // Update total
    if (opData.total !== undefined) {
      var newTotal = parseInt(opData.total, 10);
      if (newTotal > this.total) {
        this.complete = false;
        this.total = newTotal;
      }
    }
    // Update progress bar
    if (opData.val !== undefined) {
      var val = this.getProgress(opData.val, opData.incr);
      if (val !== null) {
        this.currentProgress = val;
        this.progress(val);
      }
    }
    // Update step
    if (opData.step !== undefined &&
        parseInt(opData.step, 10) < this.steps.length) {
      this.currentStep = parseInt(opData.step, 10);
    }
    // Update arguments (for step template)
    if (opData.args && this.currentStep !== null) {
      if (opData.incr === true) {
        for (var key in opData.args) {
          var cur = this.currentArgs[key];
          opData.args[key] += parseInt(cur ? cur: 0, 10);
        }
      }
      // Render template
      this.renderBody(opData.args);
      this.currentArgs = opData.args;
    }
    // Re-finish if necessary
    if ((!has_resume && this.resume_url) ||
        (!has_finished && this.finished_on)) {
      this.currentProgress = 100;
      this.finished = false;
      this.finish();
    }
  },

  renderBody: function(args) {
  /**
   * Render the body text of the operation status handler from template.
   *
   * Requires that the handler have templates in `steps` (added via `addStep`),
   * the current step is defined, and the appropriate argument substitutes are
   * found in `args`.
   *
   */
    var span = $('<span class="body"></span>');
    // Expand args list
    var extra = {
      label: this.label
    };
    $.extend(args, extra);
    if (args.total === undefined) {
      args.total = this.total;
    }
    this.elm().find('.body').remove();
    $.tmpl(this.steps[this.currentStep], args)
     .wrap(span).parent()
     .appendTo(this.elm());
  },

  getTotals: function() {
  /**
   * Retrieve the totals for an operation, if we aren't already.
   */
    if (this.totalsPending) {
      return;
    }
    var cb = $.proxy(this.message, this);
    var reset = $.proxy(function() { this.totalsPending = false; }, this);
    var settings = {
      success: cb,
      complete: reset,
      data: { oid: this.id },
      dataType: 'json'
    };
    $.ajax(this.tracker.settings.totalsUrl, settings);
  }
};


var StatusTracker = function(options) {
/**
 * Track the status of a set of background operations via the channel API.
 *
 * @param operations array An array of operation objects. See documentation for
 *                         a full list of options per operation.
 * @param options object Set of options. See documentation for the full list.
 *
 */
  // Options
  this.settings = {
    prepEl: $('<span class="prep">Preparing...</span>'),
    errorEl: $('<span class="error">Error reporting progress!</span>'),
    maxErrors: 5,
    reconnectDelay: 20000,
    operationDelay: 10000,
    missingUrl: window.STATUS_MISSING_URL,
    tokenUrl: window.STATUS_TOKEN_URL,
    clearUrl: window.STATUS_CLEAR_URL,
    opsUrl: window.STATUS_OPERATIONS_URL,
    finishedUrl: window.STATUS_FINISHED_URL,
    totalsUrl: window.UNITS_TOTALS_URL,
    domain: false,
    domainContainer: null
  };
  if (options) { 
    $.extend(this.settings, options);
  }

  // Error checks
  if (!this.settings.missingUrl || !this.settings.tokenUrl) {
    return;
  }

  // Handle missing domainContainer by creating a hidden container
  if (this.settings.domain && !this.settings.domainContainer) {
    var elm = $('<div id="statusDomainContainer" style="display:none"></div>');
    $('body').append(elm);
    this.settings.domainContainer = $('#statusDomainContainer');
  }

  this.errors = 0;
  this.seenTokens = {};
  var count = 0;

  this.bind = function(name, data, callback, onlyOps) {
  /**
   * Closure for simple handler event binding.
   *
   * @param name string Name of the event including namespace
   * @param data array Optional extra arguments to the handler
   * @param callback function The event handler
   * @param onlyOps array Only bind to events for these Operation IDs
   *
   */
    var id, realData;

    if (arguments.length == 3 && typeof(arguments[1]) === 'function') {
      onlyOps = arguments[2];
      callback = arguments[1];
      realData = [];
    } else if (arguments.length == 2) {
      realData = [];
      callback = arguments[1];
    } else { realData = data; }

   if (onlyOps) {
      for (var i = 0; i < onlyOps.length; i++) {
        $(jq(onlyOps[i])).live(name+'.status', realData, callback);
      }
    } else {
      $('.status-handler').live(name+'.status', realData, callback);
    }
  };

  this.channelOpen = function() {
  /**
   * Default handler for channel API's "onopen" event.
   *
   * Fires `connect.status`
   *
   */
    $('.status-handler').trigger('connect.status', [this]);
  };

  this.channelMessage = function(msg) {
  /**
   * Default handler for channel API's "onmessage" event.
   *
   * Calls `handler.message()` for each operation found in the message.
   *
   */
    this.resetTimeout('token');

    var parsed = JSON.parse(msg.data);
    if (typeof(parsed) !== 'object') {
      return;
    }

    var handler;
    var self = this;
    $.each(parsed, function(key, val) {
      handler = self.getHandler(key);
      handler.message(val);
    });

  };

  this.channelError = function(error) {
  /**
   * Called when the channel API triggers an "onerror" event.
   *
   * Fires `error.status`.
   *
   * @param error object Contains `description` of the error and a status
   * `code`.
   *
   */ 
    var retried = false;
    this.errors = this.errors + 1;
    if (this.errors <= this.settings.maxErrors) {
      retried = true;
      this.getToken(true);
    }
    $('.status-handler').trigger('error.status', [this, error, retried]);
  };

  this.channelClose = function() {
  /**
   * Called when the channel API triggers an "onerror" event.
   *
   * Fires `close.status`.
   *
   * TODO: What to do when channel is closed cleanly? Reconnect?
   */
   $('.status-handler').trigger('close.status', this);
  };

  this.getPostBody = function(elements) {
  /**
   * Construct a POST body.
   *
   * @param elements jQuery A set of handler elements.
   */
    var data = {};
    if (this.settings.domain) {
      data.domain = true;
    } else {
      var self = this;
      var ops = $.map(elements, function(e) { 
        var h = self.elmToHandler(e);
        return h.id;
      });
      data.operation_ids = ops;
    }
    var json = JSON.stringify(data);
    return json;
  };

  this.getToken = function(clear) {
  /**
   * Request a token from the server for the page's operation(s).
   *
   * @param clear bool Tell the server to clear the current token regardless of
   *   age/status.
   *
   */
    var json = this.getPostBody($('.status-handler'));
    var cb = $.proxy(this.gotToken, this);
    var timeout = $.proxy(function() { this.resetTimeout('token'); }, this);
    var settings = {
      type: 'post',
      data: { data: json },
      success: cb,
      complete: timeout
    };
    var url;
    if (clear) {
      url = this.settings.clearUrl;
    } else {
      url = this.settings.tokenUrl;
    }
    $.ajax(url, settings);
  };

  this.gotToken = function(token, status, xhr) {
  /**
   * Callback from getToken(): token received.
   *
   * Fires `token.status`.
   *
   * Create channel and register custom aggregation handlers.
   *
   * @param token string Token used to build GAE Channel
   * @param status int The status code (200)
   * @param xhr object jQuery's XHR object
   *
   */
    if (token === this.token) {
      if (this.seenTokens[token] === undefined) {
        this.seenTokens[token] = 1;
      } else {
        this.seenTokens[token] += 1;
      }
      if (this.seenTokens[token] < 2) {
        return;
      }
    }
    this.token = token;
    this.channel = new goog.appengine.Channel(token);
    if (this.socket) {
        this.socket.close();
    }
    this.socket = this.channel.open();
    this.socket.onopen = $.proxy(this.channelOpen, this);
    this.socket.onclose = $.proxy(this.channelClose, this);
    this.socket.onerror = $.proxy(this.channelError, this);
    this.socket.onmessage = $.proxy(this.channelMessage, this);
    $('.status-handler').trigger('token.status', this);
  };

  this.forget = function(handler, force) {
  /**
   * An operation has completed.
   *
   * For non-domain trackers, forget its handler and get a new channel.
   * Otherwise, get a new operation list.
   *
   * Also, inform the backend that it has completed. If it has no resume_url,
   * its UI may be removed.
   *
   * @param handler object A handler for a completed operation.
   */
    if (!handler.resume_url) {
      handler.removeUI();
      handler.elm().remove();
    }
    var callback = function(data, status, xhr) {
      if (this.settings.domain) {
        this.getDomainOps();
      } else {
        this.getToken();
      }
    };
    $.post(this.settings.finishedUrl,
       { operation_id: handler.id, force: force },
       $.proxy(callback, this)
    );
  };

  this.getDomainOps = function() {
  /**
   * Issue XHR to get a list of managed domain-wide operations.
   */
    var cb = $.proxy(this.gotDomainOps, this);
    var timeout = $.proxy(function() { this.resetTimeout('ops'); }, this);
    var settings = {
      success: cb,
      complete: timeout,
      dataType: 'json'
    };
    $.ajax(this.settings.opsUrl, settings);
  };

  this.gotDomainOps = function(ops, status, xhr) {
  /**
   * Callback: Domain operations received.
   *
   */
    var op;
    var seen = [];

    var justFinished = getParameterByName('statusJustFinished');
    if (justFinished) {
      justFinished = justFinished.split(',');
    } else {
      justFinished = [];
    }

    for (var o = 0; o < ops.length; o++) {
      op = ops[o];
      if (justFinished.indexOf(op.id) !== -1) {
        continue;
      }
      handler = this.getHandler(op);
      if (!handler.hasUI()) {
        handler.buildUI();
      }
      seen.push(op.id);
    }
    // Remove/finish operations that are now gone
    var toFinish = $('.status-handler').filter(function(i) {
      var $t = $(this);
      if (justFinished.indexOf(($t.data('id') || $t.attr('id'))) !== -1) {
        return false;
      }
      var gone = seen.indexOf($t.data('id')) === -1;
      var isFinished = Boolean($t.data('finished_on'));
      return gone || isFinished;
    });
    for (var k = 0; k < toFinish.length; k++) {
      handler = this.elmToHandler(toFinish[k]);
      if (handler.currentProgress < 100 || op.missing) {
        if (!handler.missing && !handler.resume_url && !handler.finished_on) {
          this.checkMissing(handler.id);
        } else {
          handler.progress(100);
        }
      }
    }
  };

  this.checkMissing = function(oid) {
  /**
   * Check for additional information about an incomplete Operation.
   *
   * This is called when an Operation is marked as complete with neither a
   * resume URL or finished date stamp.
   *
   */
    var cb = $.proxy(this.gotDomainOps, this);
    var settings = {
      success: cb,
      data: { oid: handler.id },
      dataType: 'json'
    };
    $.ajax(this.settings.missingUrl, settings);
  };

  this.elmToHandler = function(elm) {
  /**
   * Given an element, configure it to be suitable for handler creation.
   */
    elm = $(elm);
    if (!elm.data('id')) {
      elm.data('id', elm.attr('id'));
    }
    return this.getHandler(elm.data());
  };

  this.getHandler = function(op) {
  /**
   * Get a Handler object for a given Operation.
   *
   * This will either construct a new DOM element to represent the Operation,
   * or use an existing one. It will update its attributes with the attributes
   * in `op`.
   *
   * @param op object New/initial Operation specification
   *
   */
    if (typeof(op) === 'string') {
      op = { id: op };
    }
    var init, methods = {};

    var container = this.settings.domainContainer;
    var handler = $(jq(op.id));
    if (handler.length === 0) {
      handler = $('<div style="display:none" id="'+op.id+
                  '" class="status-handler"/>');
      container.append(handler);
    }
    if (!handler.data('init')) {
      init = handlerInit;
      methods = handlerMethods;
    }
    op.tracker = this;
    $.extend(true, handler.data(), op, init, methods);

    // Prevent infinite loops due to never nullifying "missing" hint
    if (op.missing === undefined) {
      handler.data('missing', null);
    }

    return handler.data();
  };

  this.start = function() {
  /**
   * Get operations, initialize handlers, retrieve token, setup timeouts.
   */
    var op;

    // Create global element to hook onto
    if (this.settings.domain) {
      this.getDomainOps();
    } else {
      var self = this;
      $('.status-handler').each(function() {
        var handler = self.getHandler({ id: $(this).attr('id') });
        if (handler) {
          handler.buildUI();
        }
      });
    }
    this.getToken();
  };

  this.resetTimeout = function(name) {
  /**
   * Reset a named timeout.
   */
    if (name === 'token') {
      $.doTimeout(name, this.settings.reconnectDelay,
                  $.proxy(this.getToken, this));
    }
    if (name === 'ops') {
      $.doTimeout('ops', this.settings.operationDelay,
                  $.proxy(this.getDomainOps, this));
    }
  };

  this.handlerOption = function(id, key, value) {
  /**
   * Set an option on a handler.
   *
   * @param id string The Operation ID
   * @param key string The attribute name
   * @param value string The new attribute value
   *
   */
   var handler = this.getHandler(id);
   handler[key] = value;
  };
};

