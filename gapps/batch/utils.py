import random
import logging

def chunk_it(l, n):
    """
    Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

def pair_up(args):
    """
    Splits an iterable into pairs.

    >>> pair_up((1, 2, 3, 4))
    [(1, 2), (3, 4)]
    """
    zargs = [iter(args)] * 2
    return zip(*zargs)

def get_batch_id(op_or_chunk):
    """
    Given a :class:`gapps.models.BatchOperation` or
    :class:`gapps.models.BatchChunk`, get the corresponding ``batch_id``.
    """
    return getattr(op_or_chunk, 'batch_id', None) or op_or_chunk.key().id()

def get_delay(count):
    """
    Calculates a delay in seconds based on how many times this chunk has
    already been delayed + randomly chosen number of seconds between 5 and 15
    """

    delay = 1 + (2 * max(1, count)) + random.randint(5,15)
    logging.info('Delaying the execution of the chunk by %d seconds', delay)
    return delay


def get_handler(batch_obj):
    """
    Return a BatchOperation/BatchChunk handler ready to be used.

    :param batch_obj: The :class:`gapps.models.BatchOperation` or
        :class:`gapps.models.BatchChunk` to get a handler for.
    """
    try:
        handler = HANDLERS[batch_obj.op_name]
    except KeyError:
        raise KeyError('No BatchOperation Handler for key `%s`' % batch_obj.op_name)
    else:
        return handler(batch_obj)

def register_handler(key, cls):
    """
    Register a ``BatchOperation`` handler class ``cls`` as ``key``.
    """
    HANDLERS[key] = cls


HANDLERS = {}

