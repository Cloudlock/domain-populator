def dbg():
    """ Enter pdb in App Engine

    Re-enable system streams for it.

    In order to set a break point put the following line in code:

    from admin.debug import dbg; dbg()

    """
    import pdb
    import sys
    pdb.Pdb(stdin=getattr(sys,'__stdin__'),stdout=getattr(sys,'__stderr__')).set_trace(sys._getframe().f_back)
