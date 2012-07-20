from __future__ import division, with_statement

import logging
import random
import traceback
import itertools
import pickle
#import json
import urllib
from copy import copy
from datetime import datetime

from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import simplejson
from django.utils.safestring import mark_safe
from django.utils import simplejson
from gapps import enqueue
from google.appengine.ext import db
from gapps.batch.utils import get_batch_id, chunk_it, get_delay, register_handler
from gapps.models import BatchChunk, BatchOperation, DomainSetup,DomainUser
from gapps.models import BatchUnitError, NumDocSetup, DocTypeSetup, ShareSetup, ServiceHelper
from gapps.models import BatchCheckpoint, NumSiteSetup
from gdata.client import RequestError
from gdocsaudit import docutils, tools, sitesutils
from google.appengine.api import mail, memcache
from gapps.docnames import doclist
from gapps.usernames import user_list
from gdata.docs.data import DATA_KIND_SCHEME
import gdata.docs.data
import gdata.apps.service
import gdata.apps.adminsettings.service


from google.appengine.api import channel



__all__ = ['BaseHandler', 'CreateDocsForOwner','ShareDocument','BatchListOfOwners', 'CreateLargeExposure']


class ChunkDelayed(Exception):
    """
     Raised when a chunk has been delayed; do not enqueue it again!
     """
    def __init__(self, chunks):
        self.chunks = chunks


class ChunkUnitError(Exception):
    """
     To be raised during the processing of a chunk unit.

     Contains a bit of logic to decide if an error should be ignored, is in
     response to a rate limit, etc.
     """
    #: We don't retry on these codes
    noretry = [404]
    #: We consider these code to be rate limit hits
    ratelimit = [403, 503, 400, 500]
    #: Is this based on a RequestError?
    is_reqerr = False

    def __init__(self, unit, chunk, code=0, msg='', req=None):
        self.unit = unit
        self.chunk = chunk
        self.is_reqerr = bool(req)
        if req:
            self.code = req.status
            self.msg = req.body
        else:
            self.code = code
            self.msg = msg

    def should_retry(self):
        """
        Can this error be retried?
        """
        return (not self.code in self.noretry) and not "You can't yet" in self.msg

    def is_rate_limit(self):
        """
        Is this error considered a rate limit hit?
        """
        return self.code in self.ratelimit \
               and not "You can't yet" in self.msg

    def __unicode__(self):
        return 'Unit %s of BatchChunk #%s: %s' % (self.unit,
                                                  self.chunk.key().id(),
                                                  self.error)


class ChunkUpdateError(ChunkUnitError):
    """
    An error occurred when trying to "get then update" the chunk.
    """


class DeferFinish(Exception):
    """
    Don't bother trying to finish the chunk/op yet; we know it isn't done.
    """


class BaseHandler(object):
    """
     The base handler for all Batch Operations. Any new handler should inherit
     from me, and implement the following methods:

     * :meth:`build_chunks`
     * :meth:`do_unit`

     You may also wish to provide alternative methods for those labeled
     *Callback*. Though you should avoid overriding ones beginning with an
     underscore!

     Other considerations:

     * My :attr:`key` attribute is incredibly important: it serves as the lookup
       key for finding me! It is set on :attr:`BatchOperation.op_name` and used
       to generate an instance of me to handle the associated operation. Its
       value must be unique among all handlers.

     * New handlers must be registered using
       :func:`gapps.batch.utils.register_handler`.

     * Handlers are not meant to start operations directly, instead
       deferring that task to :meth:`BatchOperation.start`. If you override my
       :meth:`__init__` in order to start a job, horrible things may happen.

     """
    #: User-friendly name for this type
    op_label = 'Batch Operation'
    #: User-friendly unit label for this type
    unit_label = 'Unit'
    #: User-friendly verbose unit label for this type
    unit_label_verbose = 'Units'
    #: Used to get a handler via :func:`utils.get_handler`
    key = 'test'
    #: Maximum number of retries *per unit*
    max_retries = 5
    #: Do we automatically retry err units?
    auto_retry = True
    #: Do we queue retries or do them immediately?
    queue_retry = True
    #: The BatchOperation associated with this handler
    batch = None
    #: Set during init; used to determine if the operation has been delayed
    delay_key = ''
    #: Maximum number of times to delay a chunk
    delay_max = 7
    #: Custom logger created at instantiation; use me instead of ``logging``
    log = None

    def __init__(self, batch):
        """
          :param batch: The BatchChunk or BatchOperation to bind to this handler.
          """
        if isinstance(batch, BatchChunk):
            self.batch = BatchOperation.get_by_id(batch.batch_id)
        else:
            self.batch = batch

        self.delay_key = ':'.join(('delay', str(self.batch.key().id())))
        #self.log = self.get_logger()

    def get_logger(self, name='batch', single_handler=True, cls=logging.Logger,
                   **kwargs):
        """
        Create an AppEngine-friendly logger.

        The logger will (a) not duplicate log messages in the root logger and
        (b) ensure entries are logged at their proper level.

        :param cls: A custom logger class
        :param single_handler: Enforce that the logger only ever has one handler?
        :param kwargs: Any attributes to set on the instantiated ``cls``. This
            hack allows us to have "special" loggers that have access to more
            than a ``name`` attribute.
        """
        logging.setLoggerClass(cls)
        # Filter out messages not meant for the root logger
        root = logging.getLogger()
        if len([f for f in root.handlers[0].filters if f.name == 'root']) == 0:
            filtr = logging.Filter('root')
            root.handlers[0].addFilter(filtr)
        formatter = logging.Formatter('%(name)-6s: %(levelname)-8s %(message)s')
        # GAE-specific stream handler
        handler = AppLogsHandler()
        handler.setFormatter(formatter)
        log = logging.getLogger(name)
        if single_handler and len(log.handlers) > 0:
            log.handlers[0] = handler
        else:
            log.addHandler(handler)
        for key, val in kwargs.items():
            setattr(log, key, val)
        # Reset logger class
        logging.setLoggerClass(logging.Logger)
        return log

    def get_followup_url(self):
        """
        Used to redirect to a custom status page following a batch operation.

        .. warning::

           DEPRECATED
        """
        pass

    def batch_starting(self):
        """
          *Callback*

          Called immediately before a batch is first started. Generally used to
          modify `self.batch`.
          """
        pass

    def batch_done(self):
        """
          *Callback*

          Called immediately after a BatchOperation has completed.
          """
        pass

    def build_chunks(self, checkpoint=None):
        """
          *Callback*

          Build chunks for a batch operation.

          Chunks can be built from BatchOperations or existing BatchChunks. By
          default, this method isn't very useful and should be overriden by sub-
          classes.

        .. warning::

           Due to internal usage during this stage, you should consider
           ``self.batch`` to be read-only!

        :param checkpoint: The :class:`gapps.models.BatchCheckpoint` object
            associated with this operation, if any. Generally only provided if
            this isn't the first time chunks are being built for this operation.
        :returns: generator which yields BatchChunks
        """
        batch_id = get_batch_id(self.batch)
        chunk = self.get_chunk_clone()
        yield chunk

    def _build_chunks(self):
        """
        I take care of common setup tasks for chunk building. Don't mess with
        me!
        """
        cp = BatchCheckpoint.all().filter('batch_id', self.batch.key().id())
        cp = cp.fetch(1)
        checkpoint = cp[0] if len(cp) > 0 else None

        # Mark operation as building
        self.batch.building = True
        self.batch.put()

        self.batch.started_on = datetime.now()

        for chunk in self.build_chunks(checkpoint):
            yield chunk

        # If we get through all the chunks, consider the task complete.
        if checkpoint is not None:
            checkpoint.delete()

        # Mark operation as done building
        self.batch.building = False
        self.batch.put()

    def process_chunk(self, chunk, count=1):
        """
          Process ``count`` units in ``chunk``.
          """
        real_count = 0
        if self.finished(chunk):
            return False
        if count is None or count == 0:
            count = len(chunk.units_pending)
        for i in range(count):
            try:
                if self.delayed():
                    break
                unit = self.get_unit(chunk)
                if unit:
                    self._process_unit(unit, chunk)
                    real_count += 1
                chunk = chunk.reload()
            except DeferFinish:
                pass
            else:
                self.finish(chunk)
            finally:
                if real_count != 0:
                    logging.info('Processed %d units from chunk #%s: (%d, %d, %d)',
                                 real_count, chunk.key().id(), len(chunk.units_pending),
                                 len(chunk.units_done), len(chunk.units_error))

    def chunk_done(self, chunk):
        """
        *Callback*

        Called when a chunk has been finished.
        """
        pass

    def _process_unit(self, unit, chunk):
        """
          Handles the actual flow of processing a unit, from changing its location
          in the BatchChunk to handling errors.

        You probably won't need to override this.
        """
        success = False
        try:
            try:
                self.do_unit(unit, chunk)
                success = True
            except Exception, e:
                if isinstance(e, RequestError):
                    err = ChunkUnitError(unit=unit, chunk=chunk, req=e)
                else:
                    err = ChunkUnitError(unit=unit, chunk=chunk,
                                         msg=traceback.format_exc())

                # Callback
                try:
                    self.unit_error(unit, chunk, err)
                    success = True
                except ChunkUnitError, e:
                    if e.is_rate_limit():
                        self.handle_rate_limit(unit, chunk, e)
                        return # In case handle_rate_limit() didn't raise
                    raise
                except Exception, e:
                    raise
            self.finish_unit(unit, chunk)
        except ChunkDelayed:
            raise
        except Exception, e:
            if not isinstance(e, ChunkUnitError):
                err = ChunkUnitError(unit, chunk, msg=traceback.format_exc())
            else:
                err = e
            self.err_unit(err)
        finally:
            self.unit_done(unit, chunk, success)

    def do_unit(self, unit, chunk):
        """
          *Callback*

          Do the actual processing of a chunk unit.

          Sub-classes must override.
          """
        raise NotImplementedError()

    def get_unit(self, chunk):
        """
        Grab a work unit off the ``chunk`` stack to work on.
        """
        try:
            unit = random.choice(chunk.units_pending)
        except IndexError:
            self.finish(chunk)
            return None
        else:
            return unit

    def finish_unit(self, unit, chunk, start_next=False):
        """
          Mark a ``chunk`` ``unit`` as complete and delete its error log.

          Automatically called by :meth:`_process_unit` if an exception is not
          raised.

        :param dest: Destination queue for the unit; pending, done, or error
        """
        _, chunk = self.move_unit(chunk, 'pending', 'done', units=[unit]) 
        chunk.delay_count = 0
        chunk.put()

        # Clear possible error for this unit
        errors = BatchUnitError.all().filter('chunk_id',
                                             chunk.key().id()).filter('unit',
                                                                      unit)
        if len(list(errors)) != 0:
            errors[0].delete()

    def err_unit(self, err, retry=True):
        """
          Log and mark a ``unit`` of ``chunk`` as having error ``err``.

          Depending on configuration, the unit may also be retried (indirectly,
          by putting it back on the pending stack and queuing or processing
          the chunk directly).

          :param retry: Do we retry the ``err`` unit? This overrides all other
              retry preferences.

        TODO: differentiate between expected and unexpected errors.
        """
        unit, chunk = err.unit, err.chunk
        errstring = 'Error for unit %s in chunk #%s (%d, %d, %d) of batch #%s: %s'
        logging.error(errstring, unit, chunk.key().id(),
                      len(chunk.units_pending), len(chunk.units_done),
                      len(chunk.units_error), chunk.batch_id, unicode(err.msg))

        try:
            self.move_unit(chunk, 'pending', 'error', units=[unit])
        except ChunkUpdateError: #already moved thanks to force finish
            pass

        error = BatchUnitError.get_for(unit, chunk)
        error.message = err.msg
        error.code = err.code
        error.put()

        if retry and err.should_retry() and self.auto_retry and error.retries < self.max_retries:
            logging.info('Retrying error: %s', error)
            error.retry(queue=self.queue_retry, now=not self.queue_retry)
            if self.queue_retry:
                raise DeferFinish()

    def unit_done(self, unit, chunk, success):
        """
        *Callback*

        The unit is done. This is guaranteed to be called once per unit
        regardless of its final state.

        :param success: Whether or not the task succeeded. Rate limits are
            considered failures.
        :type success: bool
        """
        pass

    def unit_error(self, unit, chunk, err):
        """
        *Callback*

        A unit has raised an exception.

        After processing the error, be sure to re-raise an instance of
        :class:`ChunkUnitError` to continue error processing. Returning assumes
        you have resolved the issue and the unit will be marked as finished.

        :param err: The processed error raised
        :type err: ChunkUnitError
        :param unit: The unit attempted
        :param chunk: The unit's chunk
        :raises: :class:`ChunkUnitError` to continue error processing; any
            other Exception becomes the new base exception
        """
        raise err

    def finish(self, chunk=None, force=False):
        """
          Complete our batch, the supplied ``chunk`` or both.

        A BatchChunk is considered finished when it has no pending units. A
        batch is considered finished when it has no pending BatchChunks to
        complete.
        
        :param force: Force the chunk to be finished by putting all pending
            units into an error state.
        """
        # Handle force-finish
        if chunk and force and len(chunk.units_pending) != 0:
            units, chunk = self.move_unit(chunk, 'pending', 'skipped')
            for unit in units:
                self.err_unit(ChunkUnitError(unit, chunk, msg='Force finish!'),
                              retry=False)
            return self.finish(chunk, force=False)

        # Finish the chunk normally
        if chunk and len(chunk.units_pending) == 0:
            if not chunk.finished_on:
                chunk.finished_on = datetime.now()
                chunk.put()
                # Eat exceptions because raising in finish() is not great
                try:
                    self.chunk_done(chunk)
                except Exception:
                    logging.error('chunk_done() for Chunk #%d raised:\n%s',
                                  chunk.key().id(), traceback.format_exc())
            logging.info('Chunk #%s finished.', chunk.key().id())
            # Check consistency
            count = len(chunk.units_done) + len(chunk.units_error) + len(chunk.units_skipped)
            if count != chunk.unit_count:
                logging.critical('Chunk #%s of batch #%s lost consistency; %d != %d.',
                                 chunk.key().id(), chunk.batch_id, count,
                                 chunk.unit_count)
        # And maybe the operation, if there's no chunk or it's finished above
        if (not chunk or chunk.finished_on) and self.finished():
            self.batch.finished_on = datetime.now()
            self.batch.put()
            logging.info('Batch #%s finished', self.batch.key().id())
            # Update AdminAction
            #if self.batch.include_in_admin_action:
            #    aa = self.batch.get_admin_action()
            #    aa.status = 'succeeded'
            #    aa.put()
            self.batch_done()

    def finished(self, chunk=None):
        """
        Is the given ``chunk`` finished (or, if it's ``None``, our entire
        operation?)
        """
        # Don't attempt to finish operations still being built. Unfortunately,
        # A chunk may be processed (cache its batch op) before building is
        # complete, thus "building" will be True even when it no longer is.
        # This isn't a great fix, but it's something.
        if self.batch.building:
            self.batch = self.batch.reload()

        if chunk is not None:
            chunk = chunk.reload()
            return chunk.finished_on and len(chunk.units_pending) == 0
        elif not self.batch.building:
            my_count = self.batch.get_unfinished_chunks().count()
            if my_count == 0:
                my_children = BatchOperation.all().filter('parent_id',
                                                          self.batch.key().id())
                for child in my_children.fetch(1000):
                    if child.building or \
                       child.get_unfinished_chunks().count() != 0:
                        return False
                return True
            return False
        return False

    def handle_rate_limit(self, unit, chunk, error, queue=True):
        """
          *Callback*

          Handle a unit hitting a rate limit exception. In the default case, we
          simply delay execution of the chunk. You may want to do something
          different.

        :param unit: While processing this unit, the exception was raised
        :param chunk: The unit's owner
        :param error: The :class:`gdata.client.RequestError` instance
        :param queue: Re-enqueue the chunk?
        """
        self.delay(chunk, queue)

    def delay(self, chunk=None, queue=True, countdown=None):
        """
          Delays the BatchOperation (or ``chunk``) by ending work on its units
          and re-queuing it with a delay.

          :param chunk: A optional chunk to operate on. If none is specified, all
              unfinished chunks will be delayed.
          :param queue: Re-enqueue the chunk for later?
          :param countdown: Specify your own delay time; one will be calculated
              otherwise.
          """
        delayed = []
        if chunk is None:
            chunks = self.batch.get_unfinished_chunks()
            # Delay this entire batch
            memcache.add(self.delay_key, datetime.now(),
                         countdown or get_delay(self.batch.delay_count))
        else:
            chunks = [chunk]

        for c in chunks:
            if c.delay_count < self.delay_max:
                delay = countdown or get_delay(c.delay_count)
                c.delay_count += 1
                c.put()
                if queue:
                    enqueue.enqueue_batch_chunk(c.key().id(), delay)
                    logging.warn('Delayed chunk #%d of batch #%d for %d seconds.',
                                 c.key().id(), self.batch.key().id(), delay)
                else:
                    logging.warn('Delayed chunk #%d of batch #%d indefinitely.',
                                 c.key().id(), self.batch.key().id())
                delayed.append(c)
            else:
                logging.warn('Chunk #%d of batch #%d delayed too many times; finishing.',
                             c.key().id(), self.batch.key().id())
                self.finish(chunk=c, force=True)


        raise ChunkDelayed(delayed)

    def delayed(self):
        """
          Determine if the batch operation itself is delayed.
          """
        return bool(memcache.get(self.delay_key))

    def progress(self):
        """
          Get the progress of a batch operation.

          :return: dict of the form::

           { label: Foo, label_verbose: Foos, pending: [...], done: [...], error: [...], skipped: [...] }

        """
        ret = { 'label': self.unit_label,
                'label_verbose': self.unit_label_verbose,
                'op_label': self.op_label }
        bp = self.batch.progress()
        ret.update(bp)
        return ret

    def args_description(self):
        """
        Get a human-readable HTML string description of this operation's
        parameters.  For example, in a Transfer of Ownership operation, this
        should say "Transferring documents owned by bob to alice."
        """
        return ' '.join(self.batch.op_args).title()

    def move_unit(self, chunk, from_queue, to_queue, units=None):
        """
        Get a BatchChunk then move ``units`` among its queues.

        :param chunk: The BatchChunk to reload
        :param unit: The units to move
        :param from_queue: The queue the unit should come from; pending, done,
            or error
        :param to_queue: The queue the unit should go to; pending, done,
            or error
        """
        return db.run_in_transaction(self._trans_move_unit, chunk,
                                     from_queue, to_queue, units)

    def get_chunk_clone(self):
        """
        Clone ``self.batch`` into a :class:`BatchChunk` instance, copying
        over shared fields.
        """
        batch_id = get_batch_id(self.batch)
        chunk = BatchChunk(batch_id = batch_id,
                           domain = self.batch.domain,
                           op_name = self.batch.op_name,
                           op_args = self.batch.op_args,
                           big_arg = self.batch.big_arg)
        return chunk

    def set_checkpoint(self, **kwargs):
        """
        Call this method with the described arguments to enable checkpointing
        for a handled operation type.

        :param kwargs: Keyword arguments that will be provided to the next
            chunk builder.
        """
        return BatchCheckpoint.set_checkpoint(self.batch,
                                              *itertools.chain(*kwargs.items()))

    @staticmethod
    def _trans_move_unit(chunk, from_queue, to_queue, units):
        """
        Transactional method to run during :meth:`move_unit`.

        See associated method for arglist.
        """
        other_queue_name = 'error' if to_queue == 'done' else 'done'
        chunk = chunk.reload()
        from_attr = getattr(chunk, 'units_'+from_queue)
        to_attr = getattr(chunk, 'units_'+to_queue)
        other_queue = getattr(chunk, 'units_'+other_queue_name)
        if units is None:
            units = copy(from_attr)

        for unit in units:
            unit = str(unit)
            if unit not in from_attr:
                msg = 'Unit %s not found in chunk #%s\'s `%s` queue!' % (unit,
                                                                         chunk.key().id(),
                                                                         from_queue)
                raise ChunkUpdateError(unit, chunk, msg=msg)
            if unit in other_queue:
                msg = ('Unit %s of chunk #%s cannot go to queue `%s`; '
                      'already in `%s`.') % (unit, chunk.key().id(), to_queue,
                                             other_queue)
                raise ChunkUpdateError(unit, chunk, msg=msg)

            if unit in from_attr:
                from_attr.remove(unit)
            if unit not in to_attr:
                to_attr.append(unit)

        chunk.latest_activity = datetime.now()
        if len(chunk.units_pending) == 0:
            chunk.finished_on = datetime.now()
        else:
            chunk.finished_on = None
        chunk.put()
        return units, chunk

########## Handlers ##################################################################

# See register_handler call at bottom of file.
class CreateDocsForOwner(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 50
    op_label = 'Create Docs For Owner'
    unit_label = 'Document'
    unit_label_verbose = 'Documents'
    key = 'createdocs'
    #num_docs_to_make = 0

    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """
        kwargs = self.batch.kwargs

        numdocsetup = NumDocSetup.get_by_key_name(self.batch.domain)

        if not numdocsetup:
            numdocsetup = NumDocSetup(key_name=self.batch.domain)
            numdocsetup.put()

        #num_docs_to_make = 1
        percent = random.randint(1,100)

        if percent < numdocsetup.numdocs300to125:
            #300 - 125
            self.batch.num_docs_to_make = random.randint(125,300)
        elif percent < numdocsetup.numdocs125to75:
            #125 - 75
            self.batch.num_docs_to_make = random.randint(75,125)
        elif percent < numdocsetup.numdocs75to25:
            # 75 - 25
            self.batch.num_docs_to_make = random.randint(25,75)
        elif percent < numdocsetup.numdocs25to10:
            # 25 - 10
            self.batch.num_docs_to_make = random.randint(10,25)
        elif percent < numdocsetup.numdocs10to5:
            # 10 - 5
            self.batch.num_docs_to_make = random.randint(5,10)
        else:
            # 5 - 1
            self.batch.num_docs_to_make = random.randint(1,5)

        #self.batch.num_docs_to_make = 1

        logging.info("Number of docs being made for owner: %s docs for %s" % (self.batch.num_docs_to_make, kwargs['owner']))

        if numdocsetup.doccount > numdocsetup.limit or numdocsetup.doccount > numdocsetup.userlimit:
            logging.warning("Doc Limit hit - don't create any more docs")
            self.batch.num_docs_to_make = 0
        else:
            numdocsetup.doccount += self.batch.num_docs_to_make
            numdocsetup.put()

        logging.info("Number of documents to be created: %s" % self.batch.num_docs_to_make)

        #folder = kwargs.get('folder', None)
        #if folder and not docutils.is_resource_id(folder):
        #	owner =  kwargs['to']
        #	real_folder = docutils.get_or_create_doc(owner, self.batch.domain,
        # 												folder)
        
        #self.batch.set_op_arg('num_docs_to_make', num_docs_to_make)

    def batch_done(self):
        context = {}


        logging.info("Batch Done: Create Docs")

        progress = self.progress()


        numdocsetup = NumDocSetup.get_by_key_name(self.batch.domain)

        #TODO if the global limit is hit update the total progress
#        if numdocsetup.userlimit < numdocsetup.limit:
#            total_num_to_create = numdocsetup.progress_total
#        else:
#            total_num_to_create = numdocsetup.progress_total
        total_num_to_create = numdocsetup.progress_total


        current_progress = int((numdocsetup.progress_doccount / total_num_to_create) * 75) + 25

        if current_progress >= 100:
            current_progress = 99

        progress['progress_pct'] = current_progress

        message = simplejson.dumps(progress)
        id = str(self.batch.domain + "status")
        try:
            channel.send_message(id, message)
        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
            pass

        if numdocsetup.doccount < numdocsetup.userlimit and numdocsetup.doccount < numdocsetup.limit:
            logging.info("Starting new batch op for creating docs")

            #ds = DomainSetup.get_for_domain(domain)
            kwargs = {
                'owner': self.batch.kwargs['owner'],
                #'domain': domain,
                #'doc_id': new_doc.resource_id.text,
            }
            op = BatchOperation(
                domain = self.batch.domain,
                started_by = self.batch.started_by,
                op_name = 'createdocs',
                op_args = list(itertools.chain(*kwargs.items())),
                parent_id = get_batch_id(self.batch)
            )
            op.put()

            batch_id = op.key().id()
            enqueue.enqueue_batch_start(batch_id)


        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        owner = self.batch.kwargs['owner']
        count = self.batch.num_docs_to_make

        while True:
        #docs = DomainDocument2.all().filter('domain', self.batch.domain)\
        #							.filter('owner', from_email)\
        #							.filter('doc_type !=', 'folder')\
        #							.fetch(limit=self.chunk_size,
        #								   offset=num_chunks * self.chunk_size)

            if count == 0:
                break
            if count < self.chunk_size:
                current_chunk_size = count
            else:
                current_chunk_size = self.chunk_size
            count -= current_chunk_size

            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)
            chunk.units_pending = [str(i) for i in range(current_chunk_size)]
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):
        owner = chunk.kwargs['owner']
        domain = chunk.domain
        #to_user = chunk.kwargs['to']
        #folder = chunk.kwargs.get('folder_id', None)

        #TODO create document here
        #take name from docnames file
        #use random numbers to get indexes




        word1 = random.choice(doclist)
        word2 = random.choice(doclist)
        word3 = random.choice(doclist)

        title = '%s %s %s' % (word1, word2, word3)

        doctypesetup = DocTypeSetup.get_by_key_name(self.batch.domain)

        if not doctypesetup:
            doctypesetup = DocTypeSetup(key_name=self.batch.domain)
            doctypesetup.put()



        percent = random.randint(1,100)

        if percent < doctypesetup.docratio:
            #Doc
            doc_type = gdata.docs.data.DOCUMENT_LABEL
        elif percent < doctypesetup.spreadratio:
            # Spreadsheet
            doc_type = gdata.docs.data.SPREADSHEET_LABEL
        elif percent < doctypesetup.presratio:
            # Presentation
            doc_type = gdata.docs.data.PRESENTATION_LABEL
        elif percent < doctypesetup.pdfratio:
            # pdf
            doc_type = 'pdf'
        else:
            # folder
            doc_type = gdata.docs.data.FOLDER_LABEL

        batch_id = get_batch_id(self.batch)

        if doc_type == 'pdf':
            new_doc = docutils.create_pdf(owner, domain, title, batch_id)
        elif doc_type == gdata.docs.data.FOLDER_LABEL:
            new_doc = docutils.create_folder(owner, domain, title,doc_type)
            if new_doc:
                memcache.set('folder_id:%s' % batch_id, new_doc.resource_id.text)
                memcache.set('folder_limit:%s' % batch_id, random.randint(1,5))
        else:
            new_doc = docutils.create_empty_doc(owner,domain, title, batch_id, doc_type)

        #TODO what do you do if it's a folder

        #run all the shares here or create yet another batch for that?


        numdocsetup = NumDocSetup.get_by_key_name(self.batch.domain)
        #TODO might need to create new tasks just to share domain and public and outside domain

        if new_doc:
            logging.info("Document created, now sharing")

            #TODO how to create a new batch while in this batch...this is getting confusing
            kwargs = {
                'owner': owner,
                #'domain': domain,
                'doc_id': new_doc.resource_id.text,
                'email': self.batch.started_by,
            }
            op = BatchOperation(
                domain = domain,
                started_by = owner,
                op_name = 'sharedocs',
                op_args = list(itertools.chain(*kwargs.items())),
                parent_id = self.batch.parent_id
            )
            op.put()

            batch_id = op.key().id()
            enqueue.enqueue_batch_start(batch_id)
        else:
            def txn_fail():
                numdocsetup.doccount -= 1
                numdocsetup.put()
            db.run_in_transaction(txn_fail)

        def txn_add():
            numdocsetup.progress_doccount += 1
            numdocsetup.put()
        db.run_in_transaction(txn_add)



    def args_description(self):
        return mark_safe('documents created for owner <tt>%s</tt>.' % self.batch.kwargs['owner'])


# See register_handler call at bottom of file.
class ShareDocument(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 50
    op_label = 'Share Docs For Owner'
    unit_label = 'Document'
    unit_label_verbose = 'Documents'
    key = 'sharedocs'
    #num_shares = 0
    #other_share_list = []

    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """
        kwargs = self.batch.kwargs
        #num_docs_to_make = 1

        self.batch.other_share_list = []

        sharesetup = ShareSetup.get_by_key_name(self.batch.domain)

        if not sharesetup:
            sharesetup = ShareSetup(key_name=self.batch.domain)
            sharesetup.put()


        #TODO Get number of users in domain and make sure not to go over that
        
        percent = random.randint(1,100)

        if percent < sharesetup.shares20to22:
            #20-22
            self.batch.num_shares = random.randint(20,22)
        elif percent < sharesetup.shares15to20:
            # 15-20
            self.batch.num_shares = random.randint(15,20)
        elif percent < sharesetup.shares10to15:
            # 10-15
            self.batch.num_shares = random.randint(10,15)
        elif percent < sharesetup.shares5to10:
            # 5-10
            self.batch.num_shares = random.randint(5,10)
        elif percent < sharesetup.shares3to5:
            # 3-5
            self.batch.num_shares = random.randint(3,5)
        elif percent < sharesetup.shares1to3:
            # 1-3
            self.batch.num_shares = random.randint(1,3)
        else:
            # 0
            self.batch.num_shares = 0

        #self.batch.num_shares = 1

        #Try sharing with public or domain, and outside users
        othershares = random.randint(1,100) + 1

        if othershares < sharesetup.sharespublic:
            #docutils.share_public(owner,domain,new_doc.resource_id.text)
            #share with public
            self.batch.other_share_list.append('public')
        elif othershares < sharesetup.sharesdomain:
            #docutils.share_domain(owner,domain,new_doc.resource_id.text)
            #share with domain
            self.batch.other_share_list.append('domain')

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside1:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'admin@uitribe.com')
            #share with uitribe
            self.batch.other_share_list.append(sharesetup.outsideuser1)

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside2:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'aprigoqagdocs@gmail.com')
            #share with aprigoqagdocs
            self.batch.other_share_list.append(sharesetup.outsideuser2)

        #folder = kwargs.get('folder', None)
        #if folder and not docutils.is_resource_id(folder):
        #	owner =  kwargs['to']
        #	real_folder = docutils.get_or_create_doc(owner, self.batch.domain,
        # 												folder)

        #self.batch.set_op_arg('num_shares', num_shares)

        logging.info("Number of shares for doc: %s internal %s external" % (self.batch.num_shares, len(self.batch.other_share_list)))

    def batch_done(self):
        """
          Rescan the users' documents and possibly notify the receiving user
          via email.
          """
        #from gapps.views import scan_some_users
        #scan_some_users(self.batch.domain,
        #				[bkw["to"], bkw["from"]],
        #				"%s@%s" % (bkw["to"], self.batch.domain))
        context = {}

        logging.info("Batch Done: Sharing")

        logging.info("Batch_id used for channel: %s" % self.batch.parent_id)

        progress = self.progress()


        if progress['progress_pct'] == 100:
            ds = DomainSetup.get_for_domain(self.batch.domain)
            ds.scan_status = None
            ds.put()

            message = simplejson.dumps(progress)
            id = self.batch.domain + "status"
            try:
                channel.send_message(id, message)
            except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
                pass

            if not ds.email_sent:

                def txn_email():
                    #folder = bkw.get('folder_id', '')
                    #folder_name = bkw.get('folder', '')
                    #if folder:
                    #    fdoc = docutils.get_doc(folder, auth=bkw['to'], domain=self.batch.domain)
                    #    context['folder_url'] =  filter(lambda l: l.rel == 'alternate', fdoc.link)[0].href
                    #action = self.batch.get_admin_action()
                    context['num_done'] = len(progress["done"])
                    context['num_error'] = len(progress["error"]) + len(progress['skipped'])
                    context['domain'] = self.batch.domain
                    #context['detail'] = settings.DEPLOYED_URL + reverse(
                    #        "gapps-domain-admin-log-detail",
                    #        kwargs=dict(domain=self.batch.domain, pk=action.key().id()),)
                    to_email = self.batch.as_email(self.batch.kwargs['email'])
                    subject = template.loader.render_to_string("email/populator_subject.txt",
                                                               context).strip()
                    body = template.loader.render_to_string("email/populator_body.txt",
                                                            context)
                    mail.send_mail(sender=settings.SERVER_EMAIL, to=[to_email],
                                   subject=subject, body=body)

                    ds.email_sent = True
                    ds.put()
                db.run_in_transaction(txn_email)



        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        #user_count = self.batch.num_shares
        ds = DomainSetup.get_for_domain(self.batch.domain)
        ds_users = int(ds.num_users)
        if self.batch.num_shares >= ds_users and ds_users != 0:
            self.batch.num_shares = ds_users - 1
        count = self.batch.num_shares + len(self.batch.other_share_list)

        while True:
            #TODO definitely need to test this

            if count == 0:
                break

            if self.batch.num_shares > self.chunk_size:
                #num_shares is still big enough move along normally
                current_chunk_size = self.chunk_size
                temp_units_pending = [str(i) for i in range(current_chunk_size)]
                self.batch.num_shares -= current_chunk_size
            else:
                temp_chunk_size = self.batch.num_shares + len(self.batch.other_share_list)
                if temp_chunk_size > self.chunk_size:
                    #already know num_shares is < chunk size
                    temp_units_pending = [str(i) for i in range(self.batch.num_shares)]
                    current_chunk_size = self.batch.num_shares
                    while current_chunk_size < self.chunk_size:
                        temp_units_pending.append(self.batch.other_share_list.pop())
                        current_chunk_size += 1
                else:
                    #everything can fit into this chunk now
                    temp_units_pending = [str(i) for i in range(self.batch.num_shares)]
                    for user in self.batch.other_share_list:
                        temp_units_pending.append(user)
                    current_chunk_size = len(temp_units_pending)
                self.batch.num_shares = 0
            count -= current_chunk_size


            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)

            chunk.units_pending = temp_units_pending
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):
        owner = chunk.kwargs['owner']
        doc_id = chunk.kwargs['doc_id']
        domain = chunk.domain

        ds = DomainSetup.get_for_domain(domain)
        sharesetup = ShareSetup.get_by_key_name(self.batch.domain)
        logging.info("DomainSetup retrieved: %s", ds.domain)
        #TODO ***gets list of users based on value in memcache and resets memcache if none found
        try:
            if unit == 'domain':
                docutils.share_domain(owner,domain,doc_id)
            elif unit == 'public':
                docutils.share_public(owner,domain,doc_id)
            elif unit == sharesetup.outsideuser1:
                docutils.share_user(owner,domain,doc_id,sharesetup.outsideuser1)
            elif unit == sharesetup.outsideuser2:
                docutils.share_user(owner,domain,doc_id,sharesetup.outsideuser2)
            else:
                username = memcache.get("username")
                if username is None:
                    logging.info("Something happened and need to reset the memcache")
                    username = DomainUser.all().filter('domain =', domain).get().username

                try:
                    domain_user = DomainUser.all().filter('domain =', domain).filter('username >', username).get().username
                    if domain_user == owner:
                        domain_user = DomainUser.all().filter('domain =', domain).filter('username >', domain_user).get().username
                except:
                    logging.info("Reached end of user list, starting over.")
                    domain_user = DomainUser.all().filter('domain =', domain).get().username


                success = memcache.set("username", domain_user)
                if success:
                    logging.info("Successful memcache set")
                else:
                    logging.info("Unsuccessful memcache set")

                #TODO add share here
                docutils.share_user(owner, domain, doc_id, '@'.join((domain_user,domain)))
        except RequestError, e:
            logging.warn(e.args)
            if e.status == 409 and "user already has access to the document" in getattr(e, 'body', ''):
                pass
            elif "emails could not be sent" in getattr(e,'body',''):
                #We experienced a case when the ownership was changed but google failed to send the notification email to
                #the new owner. We don't need to consider this case as a failure
                pass
            else:
                raise



    def args_description(self):
        return mark_safe('documents created for owner')# <tt>%s</tt>.' % self.batch.kwargs['owner'])


# See register_handler call at bottom of file.
class CreateUsers(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 10
    op_label = 'Batch User Creation'
    unit_label = 'User'
    unit_label_verbose = 'Users'
    key = 'createusers'
    users_to_create = 0
    service = None


    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """



        kwargs = self.batch.kwargs

        self.users_to_create = int(kwargs['users_requested'])





    def batch_done(self):
        """
          Rescan the users' documents and possibly notify the receiving user
          via email.
          """
        bkw = self.batch.kwargs
        #from gapps.views import scan_some_users
        #scan_some_users(self.batch.domain,
        #				[bkw["to"], bkw["from"]],
        #				"%s@%s" % (bkw["to"], self.batch.domain))

        logging.info("Batch_id used for channel: %s" % self.batch.domain)
        logging.info("Batch Done: Create Users")
        progress = self.progress()
        progress['progress_pct'] = int(progress['progress_pct'] * 0.25)
        message = simplejson.dumps(progress)
        id = self.batch.domain + "status"
        try:
            channel.send_message(id, message)
        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
            pass

        logging.info("createusers progress: %s" % progress['progress_pct'])

        if progress['progress_pct'] == 25 or progress['num_total'] == 0:
            ds = DomainSetup.get_for_domain(self.batch.domain)
            ds.scan_status = None
            ds.put()

            kwargs = {
                'notify':'',
                'action':'createdocs',
                'scope': bkw.get('scope', 'created'),
            }
            op = BatchOperation(
                domain = self.batch.domain,
                started_by = self.batch.started_by,
                op_name = 'getusers',
                op_args = list(itertools.chain(*kwargs.items()))
            )
            op.put()

            batch_id = op.key().id()

            enqueue.enqueue_batch_start(batch_id)



        #possibly email
        context = {}
        if bkw.get('notify', False):
            context = bkw
            progress = self.progress()
            #folder = bkw.get('folder_id', '')
            #folder_name = bkw.get('folder', '')
            #if folder:
            #    fdoc = docutils.get_doc(folder, auth=bkw['to'], domain=self.batch.domain)
            #    context['folder_url'] =  filter(lambda l: l.rel == 'alternate', fdoc.link)[0].href
            #action = self.batch.get_admin_action()
            context['num_done'] = len(progress["done"])
            context['num_error'] = len(progress["error"]) + len(progress['skipped'])
            context['domain'] = self.batch.domain
            #context['detail'] = settings.DEPLOYED_URL + reverse(
            #        "gapps-domain-admin-log-detail",
            #        kwargs=dict(domain=self.batch.domain, pk=action.key().id()),)
            to_email = self.batch.as_email(bkw['to'])
            subject = template.loader.render_to_string("email/transfer_subject.txt",
                                                       context).strip()
            body = template.loader.render_to_string("email/transfer_body.txt",
                                                    context)
            mail.send_mail(sender=settings.SERVER_EMAIL, to=[to_email],
                           subject=subject, body=body)

        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        #owner = self.batch.kwargs['owner']
        count = self.users_to_create
        ds = DomainSetup.get_for_domain(self.batch.domain)
        higher_index=None

        while True:
        #docs = DomainDocument2.all().filter('domain', self.batch.domain)\
        #							.filter('owner', from_email)\
        #							.filter('doc_type !=', 'folder')\
        #							.fetch(limit=self.chunk_size,
        #								   offset=num_chunks * self.chunk_size)

            if count == 0:
                if higher_index:
                    ds.owner_offset = higher_index
                    ds.put()
                break

            if count < self.chunk_size:
                current_chunk_size = count
            else:
                current_chunk_size = self.chunk_size
            count -= current_chunk_size

            lower_index = ds.owner_offset + (num_chunks * self.chunk_size)
            higher_index = (lower_index + current_chunk_size)
            if(higher_index >= len(user_list)):
                higher_index = len(user_list) - 1

            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)

            users = list(user_list[lower_index:higher_index])

            chunk.units_pending = list(user_list[lower_index:higher_index])
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
#            chunk.service = self.service
            yield chunk

    def do_unit(self, unit, chunk):

        domain = chunk.domain

#        consumer_key = "aprigoninja8.appspot.com"
#        consumer_secret = "_Nd9uUq52h_7MWCfSfX2l5JN"
#
#        TOKEN = gdata.gauth.AeLoad('AccessToken')
#        TOKEN_SECRET = TOKEN.token_secret
#
#        service = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE, domain=domain)
#        service.auth_token = gdata.gauth.OAuthHmacToken(consumer_key, consumer_secret, TOKEN,
#                                               TOKEN_SECRET, gdata.gauth.ACCESS_TOKEN)

        #if self.service is None:


        INIT = {
        'APP_NAME': settings.API_CLIENT_SOURCE,
        'SCOPES': ['https://apps-apis.google.com/a/feeds/']
        }

        domain = self.batch.domain


    #        if self.users_to_create != 0 and username and password:
    #
    #            client = gdata.apps.adminsettings.service.AdminSettingsService(email='@'.join((username,self.batch.domain)), domain=self.batch.domain, password=password)
    #            client.ProgrammaticLogin()
    #
    #            max_users = client.GetMaximumNumberOfUsers()
    #            current_users = client.GetCurrentNumberOfUsers()
    #
    #
    #
    #            if max_users - current_users > self.users_to_create:
    #                self.users_to_create = self.users_to_create
    #            else:
    #                self.users_to_create = max_users - current_users


        service = gdata.apps.service.AppsService(source=settings.API_CLIENT_SOURCE, domain=self.batch.domain)

        sh = ServiceHelper.get_by_key_name(domain)

        if sh.access_token is not None:
            access_token = pickle.loads(sh.access_token)
            service.token_store.add_token(access_token)
            service.current_token = access_token
            service.SetOAuthToken(access_token)
            logging.info("access_token: %s" % access_token)



        #owner = chunk.kwargs['owner']
        #to_user = chunk.kwargs['to']
        #folder = chunk.kwargs.get('folder_id', None)

        ds = DomainSetup.get_for_domain(domain)
        if ds.user_created_count > ds.user_limit:
            return


        #access_token = gdata.gauth.AeLoad('AccessToken')
        ##oauth_token = self.service.token_store.find_token('%20'.join(INIT['SCOPES']))
        #self.service.current_token = access_token
        #self.service.SetOAuthToken(access_token)
        #if isinstance(access_token, gdata.auth.OAuthToken):


        if True:

    #        username = chunk.kwargs['username']
    #        password = chunk.kwargs['password']
    #        client = gdata.apps.service.AppsService(email='@'.join((username,domain)), domain=domain, password=password)
    #        #client = gdata.apps.adminsettings.service(email='admin@testninjagdocs.com', domain='testninjagdocs.com', password='Apr1g0Lab')
    #        client.ProgrammaticLogin()
            #ds = DomainSetup.get_for_domain(domain)
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

        logging.info("Batch_id used for channel: %s" % self.batch.domain)

        progress = self.progress()
        progress['progress_pct'] = int(progress['progress_pct'] * 0.25)
        message = simplejson.dumps(progress)
        id = self.batch.domain + "status"
        try:
            channel.send_message(id, message)
        except (channel.InvalidChannelClientIdError, channel.InvalidMessageError), e:
            pass

#        if progress['progress_pct'] == 100:
#            ds = DomainSetup.get_for_domain(self.batch.domain)
#            ds.scan_status = None
#            ds.put()







    def args_description(self):
        return mark_safe('documents created for owner <tt>%s</tt>.' % self.batch.kwargs['owner'])



# See register_handler call at bottom of file.
class DeleteDomainDocs(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 50
    op_label = 'Batch Doc Deletion'
    unit_label = 'Doc'
    unit_label_verbose = 'Docs'
    key = 'deletedomaindocs'
    owner = ""


    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """



        kwargs = self.batch.kwargs

        self.owner = kwargs['owner']





    def batch_done(self):
        """
          Rescan the users' documents and possibly notify the receiving user
          via email.
          """
        bkw = self.batch.kwargs
        #from gapps.views import scan_some_users
        #scan_some_users(self.batch.domain,
        #				[bkw["to"], bkw["from"]],
        #				"%s@%s" % (bkw["to"], self.batch.domain))

        #logging.info("Batch_id used for channel: %s" % self.batch.domain)
        logging.info("Batch Done: Delete Doc")
        progress = self.progress()
        progress['progress_pct'] = int(progress['progress_pct'])
        message = simplejson.dumps(progress)
        id = self.batch.domain + "deletedocs"
        try:
            channel.send_message(id, message)
        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
            pass

        if progress['progress_pct'] == 100:
            ds = DomainSetup.get_for_domain(self.batch.domain)
            ds.scan_status = None
            ds.put()

        #possibly email
        context = {}
        if bkw.get('notify', False):
            context = bkw
            progress = self.progress()
            #folder = bkw.get('folder_id', '')
            #folder_name = bkw.get('folder', '')
            #if folder:
            #    fdoc = docutils.get_doc(folder, auth=bkw['to'], domain=self.batch.domain)
            #    context['folder_url'] =  filter(lambda l: l.rel == 'alternate', fdoc.link)[0].href
            #action = self.batch.get_admin_action()
            context['num_done'] = len(progress["done"])
            context['num_error'] = len(progress["error"]) + len(progress['skipped'])
            context['domain'] = self.batch.domain
            #context['detail'] = settings.DEPLOYED_URL + reverse(
            #        "gapps-domain-admin-log-detail",
            #        kwargs=dict(domain=self.batch.domain, pk=action.key().id()),)
            to_email = self.batch.as_email(bkw['to'])
            subject = template.loader.render_to_string("email/transfer_subject.txt",
                                                       context).strip()
            body = template.loader.render_to_string("email/transfer_body.txt",
                                                    context)
            mail.send_mail(sender=settings.SERVER_EMAIL, to=[to_email],
                           subject=subject, body=body)

        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        owner = self.batch.kwargs['owner']
        #count = self.users_to_create
        nextLink="A"

        while True:
        #docs = DomainDocument2.all().filter('domain', self.batch.domain)\
        #							.filter('owner', from_email)\
        #							.filter('doc_type !=', 'folder')\
        #							.fetch(limit=self.chunk_size,
        #								   offset=num_chunks * self.chunk_size)


            if not nextLink:
                break


            if nextLink == "A":
                nextLink = None



            #if count == 0:
            #    break

            #if count < self.chunk_size:
            #    current_chunk_size = count
            #else:
            #current_chunk_size = self.chunk_size
            #count -= current_chunk_size

            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)

            feed, nextLink = docutils.get_users_docs(owner=owner, domain=self.batch.domain, nextLink=nextLink)


            chunk.units_pending = [entry.resource_id.text for entry in feed.entry]
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):
        domain = chunk.domain
        owner = chunk.kwargs['owner']
        #to_user = chunk.kwargs['to']
        #folder = chunk.kwargs.get('folder_id', None)

        docutils.delete_doc(owner, domain, unit, force=True, trash=True)


        #logging.info("Batch_id used for channel: %s" % self.batch.domain)

        progress = self.progress()
        progress['progress_pct'] = int(progress['progress_pct'])
        message = simplejson.dumps(progress)
        id = self.batch.domain + "deletedocs"
        try:
           channel.send_message(id, message)
        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
            pass

        if progress['progress_pct'] == 100:
            ds = DomainSetup.get_for_domain(self.batch.domain)
            ds.scan_status = None
            ds.put()




    def args_description(self):
        return mark_safe('documents created for owner <tt>%s</tt>.' % self.batch.kwargs['owner'])


# See register_handler call at bottom of file.
class GetUsers(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 100
    op_label = 'Batch Get Users'
    unit_label = 'User'
    unit_label_verbose = 'Users'
    key = 'getusers'
    #owner = ""


    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """



        kwargs = self.batch.kwargs

        #self.owner = kwargs['owner']





    def batch_done(self):
        """
          Rescan the users' documents and possibly notify the receiving user
          via email.
          """
        bkw = self.batch.kwargs

        logging.info("Get Users is complete")

        progress = self.progress()

        ds = DomainSetup.get_for_domain(self.batch.domain)

        ds.num_users = progress['num_total']
        ds.put()

        #possibly email
        context = {}

        context = bkw

        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        #owner = self.batch.kwargs['owner']
        #count = self.users_to_create
        nextLink="A"

        while True:

            if not nextLink:
                break


            if nextLink == "A":
                nextLink = None

            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)

            client = tools.get_gapps_client(self.batch.started_by, self.batch.domain, svc="prov")

            users_list, limit_remaining, nextLink = tools.get_some_users(client=client, usernames_only=False, limit=None, next_link=nextLink)

            chunk.units_pending = [u.login.user_name for u in users_list]
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):

        domain = chunk.domain
        #owner = chunk.kwargs['owner']
        #to_user = chunk.kwargs['to']
        #folder = chunk.kwargs.get('folder_id', None)
        action = chunk.kwargs['action']
        scope = chunk.kwargs['scope']

        """Returns created/updated DomainUser object, or None if we should skip it."""
        key_name = DomainUser.make_key_name(domain, unit)
        duser = DomainUser.get_by_key_name(key_name)
        if duser is None:
            duser = DomainUser(key_name=key_name, username=unit, domain=domain)
            duser.put()

            logging.info("DomainUser Value Created: %s" % unit)
        else:
            logging.info("DomainUser Already Exists: %s" % unit)

        if action == "createdocs":
            if scope == "all" or (scope == "created" and duser.created_by_us):
                logging.info("Starting new batch op for creating docs")

                #ds = DomainSetup.get_for_domain(domain)
                kwargs = {
                    'owner': unit,
                    #'domain': domain,
                    #'doc_id': new_doc.resource_id.text,
                }
                op = BatchOperation(
                    domain = domain,
                    started_by = self.batch.started_by,
                    op_name = 'createdocs',
                    op_args = list(itertools.chain(*kwargs.items())),
                    parent_id = get_batch_id(self.batch)
                )
                op.put()

                batch_id = op.key().id()
                enqueue.enqueue_batch_start(batch_id)
        elif action == "deletedocs":
            logging.info("Starting new batch op for delete docs")

            #ds = DomainSetup.get_for_domain(domain)
            kwargs = {
                'owner': unit,
                #'domain': domain,
                #'doc_id': new_doc.resource_id.text,
            }
            op = BatchOperation(
                domain = domain,
                started_by = self.batch.started_by,
                op_name = 'deletedomaindocs',
                op_args = list(itertools.chain(*kwargs.items())),
                parent_id = get_batch_id(self.batch)
            )
            op.put()

            batch_id = op.key().id()
            enqueue.enqueue_batch_start(batch_id)
        elif action == "createsites":
            logging.info("Starting new batch op for create sites")

            #ds = DomainSetup.get_for_domain(domain)
            kwargs = {
                'owner': unit,
                #'domain': domain,
                #'doc_id': new_doc.resource_id.text,
            }
            op = BatchOperation(
                domain = domain,
                started_by = self.batch.started_by,
                op_name = 'createsites',
                op_args = list(itertools.chain(*kwargs.items())),
                parent_id = get_batch_id(self.batch)
            )
            op.put()

            batch_id = op.key().id()
            enqueue.enqueue_batch_start(batch_id)


#        logging.info("Batch_id used for channel: %s" % self.batch.domain)
#
#        progress = self.progress()
#        progress['progress_pct'] = int(progress['progress_pct'] * 0.25) + 25
#        message = simplejson.dumps(progress)
#        id = self.batch.domain + "status"
#        try:
#           channel.send_message(id, message)
#        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
#            pass


#        if progress['progress_pct'] == 100:
#            ds = DomainSetup.get_for_domain(self.batch.domain)
#            ds.scan_status = None
#            ds.put()




    def args_description(self):
        return mark_safe('documents created for owner <tt>%s</tt>.' % self.batch.kwargs['owner'])



# See register_handler call at bottom of file.
class CreateSitesForOwner(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 50
    op_label = 'Create Sites For Owner'
    unit_label = 'Site'
    unit_label_verbose = 'Sites'
    key = 'createsites'
    #num_sites_to_make = 0

    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """
        kwargs = self.batch.kwargs

        numsitesetup = NumSiteSetup.get_by_key_name(self.batch.domain)

        if not numsitesetup:
            numsitesetup = NumSiteSetup(key_name=self.batch.domain)
            numsitesetup.put()

        #num_sites_to_make = 1
        percent = random.randint(1,100)

        if percent < numsitesetup.numsites300to125:
            #300 - 125
            self.batch.num_sites_to_make = random.randint(125,300)
        elif percent < numsitesetup.numsites125to75:
            #125 - 75
            self.batch.num_sites_to_make = random.randint(75,125)
        elif percent < numsitesetup.numsites75to25:
            # 75 - 25
            self.batch.num_sites_to_make = random.randint(25,75)
        elif percent < numsitesetup.numsites25to10:
            # 25 - 10
            self.batch.num_sites_to_make = random.randint(10,25)
        elif percent < numsitesetup.numsites10to5:
            # 10 - 5
            self.batch.num_sites_to_make = random.randint(5,10)
        else:
            # 5 - 1
            self.batch.num_sites_to_make = random.randint(1,5)

        self.batch.num_sites_to_make = 1

        logging.info("Number of sites being made for owner: %s docs for %s" % (self.batch.num_sites_to_make, kwargs['owner']))

        if numsitesetup.sitecount > numsitesetup.limit or numsitesetup.sitecount > numsitesetup.userlimit or numsitesetup.sitecount > 1000:
            logging.warning("Doc Limit hit - don't create any more docs")
            self.batch.num_sites_to_make = 0
        else:
            numsitesetup.sitecount += self.batch.num_sites_to_make
            numsitesetup.put()

        logging.info("Number of sites to be created: %s" % self.batch.num_sites_to_make)

        #folder = kwargs.get('folder', None)
        #if folder and not docutils.is_resource_id(folder):
        #	owner =  kwargs['to']
        #	real_folder = docutils.get_or_create_doc(owner, self.batch.domain,
        # 												folder)
        
        #self.batch.set_op_arg('num_sites_to_make', num_sites_to_make)

    def batch_done(self):
        context = {}


        logging.info("Batch Done: Create Sites")

        progress = self.progress()


        numsitesetup = NumSiteSetup.get_by_key_name(self.batch.domain)

        #TODO if the global limit is hit update the total progress
#        if numsitesetup.userlimit < numsitesetup.limit:
#            total_num_to_create = numsitesetup.progress_total
#        else:
#            total_num_to_create = numsitesetup.progress_total
#        total_num_to_create = numsitesetup.progress_total


#        current_progress = int((numsitesetup.progress_sitecount / total_num_to_create) * 75) + 25

#        if current_progress >= 100:
#            current_progress = 99

#        progress['progress_pct'] = current_progress

#        message = simplejson.dumps(progress)
#        id = str(self.batch.domain + "status")
#        try:
#            channel.send_message(id, message)
#        except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
#            pass

#        if numsitesetup.sitecount < numsitesetup.userlimit and numsitesetup.sitecount < numsitesetup.limit and numsitesetup.sitecount < 500:
#            logging.info("Starting new batch op for creating docs")

            #ds = DomainSetup.get_for_domain(domain)
#            kwargs = {
#                'owner': self.batch.kwargs['owner'],
#                #'domain': domain,
#                #'doc_id': new_doc.resource_id.text,
#            }
#            op = BatchOperation(
#                domain = self.batch.domain,
#                started_by = self.batch.started_by,
#                op_name = 'createsites',
#                op_args = list(itertools.chain(*kwargs.items())),
#                parent_id = get_batch_id(self.batch)
#            )
#            op.put()

#            batch_id = op.key().id()
#            enqueue.enqueue_batch_start(batch_id)


        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        owner = self.batch.kwargs['owner']
        count = self.batch.num_sites_to_make

        while True:
        #docs = DomainDocument2.all().filter('domain', self.batch.domain)\
        #							.filter('owner', from_email)\
        #							.filter('doc_type !=', 'folder')\
        #							.fetch(limit=self.chunk_size,
        #								   offset=num_chunks * self.chunk_size)

            if count == 0:
                break
            if count < self.chunk_size:
                current_chunk_size = count
            else:
                current_chunk_size = self.chunk_size
            count -= current_chunk_size

            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)
            chunk.units_pending = [str(i) for i in range(current_chunk_size)]
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):
        owner = chunk.kwargs['owner']
        domain = chunk.domain
        #to_user = chunk.kwargs['to']
        #folder = chunk.kwargs.get('folder_id', None)

        #TODO create document here
        #take name from docnames file
        #use random numbers to get indexes

        word1 = random.choice(doclist)
        word2 = random.choice(doclist)
        word3 = random.choice(doclist)

        title = '%s %s %s' % (word1, word2, word3)

#        doctypesetup = DocTypeSetup.get_by_key_name(self.batch.domain)

#        if not doctypesetup:
#            doctypesetup = DocTypeSetup(key_name=self.batch.domain)
#            doctypesetup.put()



        percent = random.randint(1,100)

        batch_id = get_batch_id(self.batch)

        new_site = sitesutils.create_site(owner, domain, title)

        #run all the shares here or create yet another batch for that?


        numsitesetup = NumSiteSetup.get_by_key_name(self.batch.domain)
        #TODO might need to create new tasks just to share domain and public and outside domain

        if new_site:
            logging.info("Document created, now sharing")

            #TODO how to create a new batch while in this batch...this is getting confusing
            kwargs = {
                'owner': owner,
                #'domain': domain,
                'site_id': new_site.id.text,
                'email': self.batch.started_by,
            }
            op = BatchOperation(
                domain = domain,
                started_by = owner,
                op_name = 'sharesites',
                op_args = list(itertools.chain(*kwargs.items())),
                parent_id = self.batch.parent_id
            )
            op.put()

            batch_id = op.key().id()
            enqueue.enqueue_batch_start(batch_id)
        else:
            def txn_fail():
                numsitesetup.sitecount -= 1
                numsitesetup.put()
            db.run_in_transaction(txn_fail)

#        def txn_add():
#            numsitesetup.progress_sitecount += 1
#            numsitesetup.put()
#        db.run_in_transaction(txn_add)



    def args_description(self):
        return mark_safe('documents created for owner <tt>%s</tt>.' % self.batch.kwargs['owner'])


# See register_handler call at bottom of file.
class ShareSite(BaseHandler):
    """
     Handler for managing document creation and sharing for an owner.
     """
    chunk_size = 50
    op_label = 'Share Sites For Owner'
    unit_label = 'Site'
    unit_label_verbose = 'Sites'
    key = 'sharesites'
    #num_shares = 0
    #other_share_list = []

    def batch_starting(self):
        """
          Don't duplicate folders; change the operation argument to a resource ID
          """
        kwargs = self.batch.kwargs
        #num_sites_to_make = 1

        self.batch.other_share_list = []

        sharesetup = ShareSetup.get_by_key_name(self.batch.domain)

        if not sharesetup:
            sharesetup = ShareSetup(key_name=self.batch.domain)
            sharesetup.put()


        #TODO Get number of users in domain and make sure not to go over that
        
        percent = random.randint(1,100)

        if percent < sharesetup.shares20to22:
            #20-22
            self.batch.num_shares = random.randint(20,22)
        elif percent < sharesetup.shares15to20:
            # 15-20
            self.batch.num_shares = random.randint(15,20)
        elif percent < sharesetup.shares10to15:
            # 10-15
            self.batch.num_shares = random.randint(10,15)
        elif percent < sharesetup.shares5to10:
            # 5-10
            self.batch.num_shares = random.randint(5,10)
        elif percent < sharesetup.shares3to5:
            # 3-5
            self.batch.num_shares = random.randint(3,5)
        elif percent < sharesetup.shares1to3:
            # 1-3
            self.batch.num_shares = random.randint(1,3)
        else:
            # 0
            self.batch.num_shares = 0

        #self.batch.num_shares = 1

        #Try sharing with public or domain, and outside users
        othershares = random.randint(1,100) + 1

        if othershares < sharesetup.sharespublic:
            #docutils.share_public(owner,domain,new_doc.resource_id.text)
            #share with public
            self.batch.other_share_list.append('public')
        elif othershares < sharesetup.sharesdomain:
            #docutils.share_domain(owner,domain,new_doc.resource_id.text)
            #share with domain
            self.batch.other_share_list.append('domain')

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside1:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'admin@uitribe.com')
            #share with uitribe
            self.batch.other_share_list.append(sharesetup.outsideuser1)

        othershares = random.randint(1,100)

        if othershares < sharesetup.sharesoutside2:
            #docutils.share_user(owner,domain,new_doc.resource_id.text,'aprigoqagdocs@gmail.com')
            #share with aprigoqagdocs
            self.batch.other_share_list.append(sharesetup.outsideuser2)

        #folder = kwargs.get('folder', None)
        #if folder and not docutils.is_resource_id(folder):
        #	owner =  kwargs['to']
        #	real_folder = docutils.get_or_create_doc(owner, self.batch.domain,
        # 												folder)

        #self.batch.set_op_arg('num_shares', num_shares)

        logging.info("Number of shares for doc: %s internal %s external" % (self.batch.num_shares, len(self.batch.other_share_list)))

    def batch_done(self):
        """
          Rescan the users' documents and possibly notify the receiving user
          via email.
          """
        #from gapps.views import scan_some_users
        #scan_some_users(self.batch.domain,
        #				[bkw["to"], bkw["from"]],
        #				"%s@%s" % (bkw["to"], self.batch.domain))
        context = {}

        logging.info("Batch Done: Sharing")

        logging.info("Batch_id used for channel: %s" % self.batch.parent_id)

#        progress = self.progress()


#        if progress['progress_pct'] == 100:
#            ds = DomainSetup.get_for_domain(self.batch.domain)
#            ds.scan_status = None
#            ds.put()

#            message = simplejson.dumps(progress)
#            id = self.batch.domain + "status"
#            try:
#                channel.send_message(id, message)
#            except (channel.InvalidMessageError, channel.InvalidChannelClientIdError), e:
#                pass

#            if not ds.email_sent:

 #               def txn_email():
 #                   #folder = bkw.get('folder_id', '')
 #                   #folder_name = bkw.get('folder', '')
 #                   #if folder:
 #                   #    fdoc = docutils.get_doc(folder, auth=bkw['to'], domain=self.batch.domain)
 #                   #    context['folder_url'] =  filter(lambda l: l.rel == 'alternate', fdoc.link)[0].href
 #                   #action = self.batch.get_admin_action()
 #                   context['num_done'] = len(progress["done"])
 #                   context['num_error'] = len(progress["error"]) + len(progress['skipped'])
 #                   context['domain'] = self.batch.domain
 #                   #context['detail'] = settings.DEPLOYED_URL + reverse(
 #                   #        "gapps-domain-admin-log-detail",
 #                   #        kwargs=dict(domain=self.batch.domain, pk=action.key().id()),)
 #                   to_email = self.batch.as_email(self.batch.kwargs['email'])
 #                   subject = template.loader.render_to_string("email/populator_subject.txt",
 #                                                              context).strip()
 #                   body = template.loader.render_to_string("email/populator_body.txt",
 #                                                           context)
 #                   mail.send_mail(sender=settings.SERVER_EMAIL, to=[to_email],
 #                                  subject=subject, body=body)
#
#                    ds.email_sent = True
#                    ds.put()
#                db.run_in_transaction(txn_email)



        return context

    def build_chunks(self, checkpoint=None):
        num_chunks = 0
        unit_count = 0
        batch_id = get_batch_id(self.batch)
        #user_count = self.batch.num_shares
        ds = DomainSetup.get_for_domain(self.batch.domain)
        ds_users = int(ds.num_users)
        if self.batch.num_shares >= ds_users and ds_users != 0:
            self.batch.num_shares = ds_users - 1
        count = self.batch.num_shares + len(self.batch.other_share_list)

        while True:
            #TODO definitely need to test this

            if count == 0:
                break

            if self.batch.num_shares > self.chunk_size:
                #num_shares is still big enough move along normally
                current_chunk_size = self.chunk_size
                temp_units_pending = [str(i) for i in range(current_chunk_size)]
                self.batch.num_shares -= current_chunk_size
            else:
                temp_chunk_size = self.batch.num_shares + len(self.batch.other_share_list)
                if temp_chunk_size > self.chunk_size:
                    #already know num_shares is < chunk size
                    temp_units_pending = [str(i) for i in range(self.batch.num_shares)]
                    current_chunk_size = self.batch.num_shares
                    while current_chunk_size < self.chunk_size:
                        temp_units_pending.append(self.batch.other_share_list.pop())
                        current_chunk_size += 1
                else:
                    #everything can fit into this chunk now
                    temp_units_pending = [str(i) for i in range(self.batch.num_shares)]
                    for user in self.batch.other_share_list:
                        temp_units_pending.append(user)
                    current_chunk_size = len(temp_units_pending)
                self.batch.num_shares = 0
            count -= current_chunk_size


            chunk = BatchChunk(batch_id = batch_id,
                               domain = self.batch.domain,
                               op_name = self.batch.op_name,
                               op_args = self.batch.op_args)

            chunk.units_pending = temp_units_pending
            chunk.unit_count = len(chunk.units_pending)
            chunk.put()
            unit_count += chunk.unit_count
            num_chunks += 1
            logging.info('Have created %d chunks containing %d units for batch #%s.',
                        num_chunks, unit_count, self.batch.key().id())
            yield chunk

    def do_unit(self, unit, chunk):
        owner = chunk.kwargs['owner']
        site_id = chunk.kwargs['site_id']
        domain = chunk.domain

        ds = DomainSetup.get_for_domain(domain)
        sharesetup = ShareSetup.get_by_key_name(self.batch.domain)
        logging.info("DomainSetup retrieved: %s", ds.domain)
        #TODO ***gets list of users based on value in memcache and resets memcache if none found
        try:
            if unit == 'domain':
                sitesutils.share_domain(owner,domain,site_id)
            elif unit == 'public':
                sitesutils.share_public(owner,domain,site_id)
            elif unit == sharesetup.outsideuser1:
                sitesutils.share_user(owner,domain,site_id,sharesetup.outsideuser1)
            elif unit == sharesetup.outsideuser2:
                sitesutils.share_user(owner,domain,site_id,sharesetup.outsideuser2)
            else:
                username = memcache.get("username")
                if username is None:
                    logging.info("Something happened and need to reset the memcache")
                    username = DomainUser.all().filter('domain =', domain).get().username

                try:
                    domain_user = DomainUser.all().filter('domain =', domain).filter('username >', username).get().username
                    if domain_user == owner:
                        domain_user = DomainUser.all().filter('domain =', domain).filter('username >', domain_user).get().username
                except:
                    logging.info("Reached end of user list, starting over.")
                    domain_user = DomainUser.all().filter('domain =', domain).get().username


                success = memcache.set("username", domain_user)
                if success:
                    logging.info("Successful memcache set")
                else:
                    logging.info("Unsuccessful memcache set")

                #TODO add share here
                sitesutils.share_user(owner, domain, site_id, '@'.join((domain_user,domain)))
        except RequestError, e:
            logging.warn(e.args)
            if e.status == 409 and "user already has access to the document" in getattr(e, 'body', ''):
                pass
            elif "emails could not be sent" in getattr(e,'body',''):
                #We experienced a case when the ownership was changed but google failed to send the notification email to
                #the new owner. We don't need to consider this case as a failure
                pass
            else:
                raise



    def args_description(self):
        return mark_safe('documents created for owner')# <tt>%s</tt>.' % self.batch.kwargs['owner'])


class UpdateDomainDocs(BaseHandler):
    pass

register_handler(BaseHandler.key, BaseHandler)
register_handler(CreateDocsForOwner.key, CreateDocsForOwner)
register_handler(ShareDocument.key, ShareDocument)
register_handler(CreateUsers.key, CreateUsers)
register_handler(DeleteDomainDocs.key, DeleteDomainDocs)
register_handler(GetUsers.key, GetUsers)
#register_handler(CreateLargeExposure.key, CreateLargeExposure)
#register_handler(ShareLargeExposure.key, ShareLargeExposure)
register_handler(CreateSitesForOwner.key, CreateSitesForOwner)
register_handler(ShareSite.key, ShareSite)

