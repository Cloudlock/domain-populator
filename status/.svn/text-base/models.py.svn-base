import hashlib

from django.core.serializers.json import simplejson as json
from appengine_django.models import BaseModel
from google.appengine.api import channel
from google.appengine.ext import db


class ExpiredClientError(Exception):
    """
    An OperationSet "clientID" expired.
    """
    def __init__(self, op):
        self.opset = op

    def __str__(self):
        return 'Channel expired for Subscriber: %s' % self.sub


class Operation(BaseModel):
    """
    A trackable operation.

    :param key_name: The "operation ID" (<namespace>:<id>)
    """
    #: Assign to a domain to get picked up by domain-wide trackers
    domain = db.StringProperty()
    #: Shows up above auto-configured progress bars if present
    label = db.StringProperty()
    #: Give the user follow-up URL; keeps Operation from being GC'd
    resume_url = db.StringProperty()
    tracked_since = db.DateTimeProperty(auto_now_add=True)
    finished_on = db.DateTimeProperty()


class OperationSet(BaseModel):
    """
    Represents a group of Operations.

    Because a client can only be subscribed to one channel at a time, we use
    this to aggregate subscriptions to multiple operations.

    :param key_name: The domain, if it is a "singleton" OperationSet.
    """
    static_operation_ids = db.StringListProperty()
    #: Only used for non-domain-wide sets
    domain = db.StringProperty()
    current_token = db.StringProperty(indexed=False)

    def set_operations(self, ops):
        sort_ops = sorted(ops, key=lambda i: i.key().name())
        self.operation_ids = [o.key().name() for o in sort_ops]

    def get_operations(self):
        if not getattr(self, '_operations'):
            self._operations = Operation.get(self.operation_ids)
        return self._operations

    def set_operation_ids(self, ops):
        if not self.key().name():
            self.static_operation_ids = ops

    def get_operation_ids(self):
        if self.key().name():
            return [k.name() for k in (Operation.all(keys_only=True)
                             .filter('domain', self.key().name()))]
        return self.static_operation_ids

    operations = property(get_operations, set_operations,
                          doc="The group's operations")
    operation_ids = property(get_operation_ids, set_operation_ids,
                             doc="The group's operation_ids")

    @property
    def token(self):
        """
        Get a token for this Subscriber.
        """
        if not self.current_token:
            self.current_token = channel.create_channel(self.client_id)
        return self.current_token

    @property
    def client_id(self):
        """
        Retrieve a client ID (used to make a Channel Token).
        """
        if self.domain:
            lbl = self.domain
        else:
            lbl = '|'.join(self.operation_ids)
        hsh = hashlib.md5(lbl).hexdigest()
        return hsh

    def send_message(self, msg):
        """
        Send a message through the client channel.

        :param msg: The message to send. If not a string, it will be
            JSON-encoded.
        :raises: ExpiredClientError if Google claims an invalid client ID.
        """
        msg = json.dumps(msg)
        try:
            channel.send_message(self.client_id, msg)
        except (channel.InvalidChannelClientIdError, KeyError):
            raise ExpiredClientError(self)

    @classmethod
    def get_or_create(cls, operation_ids=None, domain=''):
        """
        Create or retrieve an OperationSet for the given operation(s).

        Will also create Operations where necessary.

        :param domain: Get "singleton" OperationSet for a domain
        :param operation_ids: Sequence of operation IDs
        """
        if isinstance(operation_ids, basestring):
            operation_ids = [operation_ids]
        elif operation_ids is None:
            operation_ids = []

        for op in operation_ids:
            Operation.get_or_insert(op, domain=domain)

        if domain:
            return cls.get_or_insert(domain, domain=domain)

        query = cls.all()
        for o in operation_ids:
            query = query.filter('operation_ids', o)
        existing = query.fetch(1)
        if not existing:
            ret = cls(domain=domain, static_operation_ids=sorted(operation_ids))
            ret.put()
        else:
            ret = existing[0]

        return ret

