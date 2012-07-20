"""
Utilities for sharded counters and queues.
"""
__author__  = 'Tom Davis'
__credits__ = ['Brett Slatkin']
__email__   = 'tom@recursivedream.com'
__status__  = 'Development'
__version__ = '0.9.0'


import random
from itertools import chain
from google.appengine.ext import db
from google.appengine.api import memcache


class ShardedConfig(db.Model):
    """
    Tracks the number of shards for each named counter.
    """
    name = db.StringProperty(required=True)
    num_shards = db.IntegerProperty(required=True, default=20, indexed=False)
    min_shard = db.IntegerProperty(default=0, indexed=False)


class Shard(db.Model):
    """
    Shards for each named counter
    """
    name = db.StringProperty(required=True)
    accum = db.IntegerProperty(required=True, default=0)


class QueueShard(db.Model):
    """
    Shards for each unique named counter
    """
    name = db.StringProperty(required=True)
    accum = db.ListProperty(db.Blob, indexed=False)


class ShardedCounter(object):
    """
    A counter that is sharded among different objects in the Datastore.

    Beyond its low-level implementation, it acts the same as a normal counter.

       >>> counter = ShardedCounter('my_sharded_counter')
       >>> counter.incr()
       True
       >>> counter.count()
       1
       >>> counter.incr(5)
       True
       >>> counter.real_count()
       6

    """
    #: Key name prefix for datastore/memcache
    prefix = 'sc'
    #: Set during initialization; combination of supplied name and ``prefix``
    name = None
    #: How long to cache counts in memcache
    ttl = 10
    shard_class = Shard
    num_shards = 0
    min_shard = 0

    def __init__(self, name, num_shards=20):
        self.name = ':'.join((self.prefix, name))
        self.num_shards = num_shards

    def get_config(self, force=False):
        """
        Get/cache the configuration object for this counter.
        """
        key = '%s:config' % self.name
        cached = memcache.get(key)
        if not cached or force:
            config = ShardedConfig.get_or_insert(self.name, name=self.name,
                                                 num_shards=self.num_shards)
            memcache.set(key, config)
            cached = config

        if cached.num_shards < self.num_shards:
            self.set_shard_count(self.num_shards)
            return self.get_config(True)

        self.num_shards = cached.num_shards
        self.min_shard = cached.min_shard

        return cached

    def count(self):
        """
        Get cached or aggregate real count.
        """
        total = memcache.get(self.name)
        if total is None:
            total = self.real_count()
        return int(total)

    def real_count(self):
        """
        Get aggregate real count; cache result.
        """
        total = 0
        for counter in self.itershards():
            total += counter.accum
        memcache.add(self.name, str(total), self.ttl)
        return int(total)

    def lazy_counter(self):
        """
        Lazily iterate over each shard
        """
        for counter in self.itershards():
            yield counter.accum

    def incr(self, val=1):
        """
        Increment the value for a given sharded counter.
        """
        result = False
        config = self.get_config()
        while result == False:
            try:
                result = db.run_in_transaction(self.txn_increment, config, val)
            except db.TransactionFailedError:
                pass
            except (db.BadValueError, db.BadRequestError, db.Timeout,
                    MemoryError):
                self.set_shard_count(self.num_shards*2, self.num_shards)

        self.mc_incr(val)
        return result

    def decr(self, val=1):
        """
        Decrement the value for a given sharded counter.
        """
        self.incr(-val)

    def txn_increment(self, config, val):
        """
        Transaction: increment random counter accumulator.
        """
        index = random.randint(self.min_shard, config.num_shards - 1)
        shard_key = ':'.join((self.name, str(index)))
        counter = self.shard_class.get_by_key_name(shard_key)
        if not counter:
            counter = self.shard_class(key_name=shard_key, name=self.name)
        counter.accum += val
        counter.put()
        return True

    def mc_incr(self, val):
        """
        Increment count in memcache.
        """
        memcache.incr(self.name, initial_value=0)

    def set_shard_count(self, num, new_min=0):
        """
        Change the number of shards for a given counter.
        Will never decrease the number of shards.
        """
        config = ShardedConfig.get_or_insert(self.name, name=self.name,
                                             num_shards=self.num_shards)
        def txn():
            if config.num_shards < num:
                config.num_shards = num
                if new_min < num:
                    config.min_shard = new_min
                config.put()
            return config

        config = db.run_in_transaction(txn)
        key = '%s:config' % self.name
        memcache.delete(key)
        self.num_shards = config.num_shards
        self.min_shard = config.min_shard
        return config

    def destroy(self):
        """
        Destroy this sharded entity by removing all its shards.

        :returns: A "future" entity, capable of blocking for a result.
            The operation will complete in the background.
        """
        self.get_config().delete()
        keys = self.shard_class.all(keys_only=True).filter('name', self.name)
        return db.delete_async(keys)

    def itershards(self):
        """
        Iterate over all shards, getting multiple shards by key.

        Will grab up to 50 entities per query.
        """
        config = self.get_config()
        shard_range = xrange(config.num_shards)

        for chunk in iterchunked(shard_range, 50):
            keys = [':'.join((self.name, str(i))) for i in chunk]
            entities = filter(lambda r: r is not None,
                              self.shard_class.get_by_key_name(keys))
            random.shuffle(entities)
            for e in entities:
                yield e


class ShardedQueue(ShardedCounter):
    """
    A "last in, random out" sharded queue implementation.

       >>> queue = ShardedQueue('my_sharded_queue')
       >>> queue.add('task') #doctest: +ELLIPSIS
       <shard.QueueShard object at 0x...>
       >>> queue.pop()
       'task'

    """
    prefix = 'sq'
    shard_class = QueueShard

    def count(self, unique=False):
        """
        Get cached or aggregate real count.

        :param unique: Only count unique entities?
        """
        u = unique and ':u' or ''
        total = memcache.get(self.name + u)
        if total is None:
            total = self.real_count(unique)
        return int(total)

    def real_count(self, unique=False):
        """
        Get aggregate real count and cache.

        :param unique: Only count unique entities?
        """
        u = unique and ':u' or ''
        if unique:
            total = len(self.unique())
        else:
            total = len(list(self.items()))
        memcache.add(self.name + u, str(total), self.ttl)
        return total

    def count_greater_than(self, x):
        """
        Determine if this queue's real count is > x
        """
        total = 0
        for val in self.lazy_counter():
            total += len(val)
            if total > x:
                return True
        return False

    def items(self):
        """
        Returns a generator used to iterate over all queue items.
        """
        return chain(*(i.accum for i in self.itershards()))

    def unique(self):
        """
        Returns the set of all unique queue items.

        This implementation sacrifices speed for total memory usage.
        """
        return frozenset(self.items())

    def add(self, val):
        """
        Add one item to the queue.

        :param val: ``str``-coercable
        """
        return self.incr([db.Blob(str(val))])

    def extend(self, val):
        """
        Add multiple items to the queue.

        :param val: Sequence of ``str``-coercable
        """
        for v in val:
            self.incr([db.Blob(str(v))])

    def pop(self):
        """
        Pop an item off the queue.

        :returns: Item or None, if one cannot be found.
        """
        for shard in self.itershards():
            if shard.accum:
                try:
                    val = db.run_in_transaction(self.txn_pop,
                                                shard.key().name())
                    if val:
                        return val
                except (db.TransactionFailedError, db.Timeout):
                    pass
        return None

    def txn_increment(self, config, val):
        """
        Transactionally increment random counter accumulator.
        """
        index = random.randint(0, config.num_shards - 1)
        shard_key = ':'.join((self.name, str(index)))
        counter = self.shard_class.get_by_key_name(shard_key)
        if not counter:
            counter = self.shard_class(key_name=shard_key, name=self.name)
        old_accum = counter.accum
        counter.accum = old_accum + val
        try:
            counter.put()
            return counter
         #Various reasons for exception here:
         #  1. Value too large (no remedy, but will try) = BadValueError
         #  2. Too many indexes (list > 5000 items) = BadRequestError
         #  3. Too large to commit
         #  4. Too large to create list
        except (db.BadValueError, db.BadRequestError, db.Timeout, MemoryError):
            raise

    def txn_pop(self, key_name, value=None):
        """
        Transactionally pop a unit off the queue with ``key_name``.
        """
        shard = self.shard_class.get_by_key_name(key_name)
        if shard.accum:
            if value is None:
                val = shard.accum.pop()
            else:
                shard.accum.remove(value)
                val = value
            shard.put()
            return val
        return None

    def remove(self, value, from_queue=None):
        """
        Remove a specific value from the queue.

        WARNING: Possibly MUCH slower than pop()!

        :param from_queue: Supply a :class:`QueueShard` key name known to
            contain the value.

        :raises ValueError: If the value cannot be found.
        """
        value = db.Blob(str(value))

        if from_queue is None:
            for shard in self.itershards():
                if shard.accum and value in shard.accum:
                    from_queue = shard.key().name()

        if from_queue is not None:
            try:
                val = db.run_in_transaction(self.txn_pop, from_queue, value)
                if val:
                    return val
            except (db.TransactionFailedError, db.Timeout):
                pass

        raise ValueError('Item %s not found in queue %s' % (value, self.name))

    def mc_incr(self, val):
        memcache.incr(self.name, delta=len(val), initial_value=0)


def iterchunked(l, n):
    """
    Generate ``n`` size chunks of ``l``.
    """
    accum = []
    for i in l:
        accum.append(i)
        if len(accum) == n:
            yield accum
            accum = []
    if accum:
        yield accum

