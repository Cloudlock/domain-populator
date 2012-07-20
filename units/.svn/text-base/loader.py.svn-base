from django.utils.importlib import import_module


HANDLERS = {}
BACKENDS = {}


def get_handlers(*dotpaths):
    """
    Return an Operation handler ready to be used.

    :param dotpath: Python import path to handler
    """
    global HANDLERS
    ret = []

    for dotpath in dotpaths:
        try:
            handler = HANDLERS[dotpath]
        except KeyError:
            mod, obj = dotpath.rsplit('.', 1)
            try:
                cls = getattr(import_module(mod), obj)
                handler = HANDLERS[dotpath] = cls
            except (AttributeError, ImportError):
                raise ValueError("Cannot import handler: %s" % dotpath)
        ret.append(handler)

    return ret


def get_backend(op):
    global BACKENDS

    dotpath = op.backend

    try:
        backend = BACKENDS[dotpath]
    except KeyError:
        mod, obj = dotpath.rsplit('.', 1)
        try:
            cls = getattr(import_module(mod), obj)
            backend = BACKENDS[dotpath] = cls
        except (AttributeError, ImportError):
            raise ValueError("Cannot import backend: %s" % dotpath)

    return backend(op)


def validate_handler(dotpath):
    """
    Validate a prospective handler.
    """
    from units.handlers import BaseHandler

    handler = get_handlers(dotpath)[0]
    if not issubclass(handler, BaseHandler):
        raise ValueError('Handlers must inherit from units.handlers.BaseHandler')
    
    return True

