"""Common simple routines that convert from GData ACLs into a simple dict format used throughout our code."""

import logging

def annotate_collab_entry(entry, domains=None):
    c = entry["type"] + ":" + entry.get("value","")
    domain = entry.get("value","").split("@")[-1]

    if entry["type"] == "group":
        entry["group"] = True
        entry["css_class"] = "group"
    elif c == "user:everyone" or entry["type"]=="domain":
        entry["everyone"] = True
        entry["css_class"] = "everyone"
    elif domain in domains:
        entry["indomain"] = True
        entry["css_class"] = "indomain"
    elif c == "default:":
        entry["public"] = True
        entry["css_class"] = "public"
    else:
        entry["outside"] = True
        entry["css_class"] = "outside"

def make_collab_entry(docstr, mydomain=None, can_edit=None, is_owner=None, domains=None):
    """Return a collab dict.
    {'type': (user:|group:|domain:),
    'value': user@domain or group@domain or domain,
    ['indomain': True,]
    ['everyone': True,]
    ['public': True,]
    ['outside': True,]
    }
    """

    parts = docstr.split(":",1)
    # mkp temporary
    if docstr.find(":") == -1:
        return []

    entry = {
        "type": parts[0],
        "value": parts[1],
        }

    annotate_collab_entry(entry, domains=domains)

    if can_edit is not None:
        entry["can_edit"] = can_edit

    if is_owner is not None:
        entry["is_owner"] = is_owner
    return entry

def annotate_collab_list(mydomain, collablist, can_edit=None, is_owner=None, domains=None):
    result = []

    for c in collablist:
        result.append(make_collab_entry(
            c, can_edit=can_edit, is_owner=is_owner, domains=domains))

    return result


def set_ex(out, key, value=True):
    # TODO: check for __getitem__ instead of dict?
    if isinstance(out, dict):
        out[key] = value
        return out
    setattr(out, key, value)
    return out

def inc_ex(out, key):
    # TODO: check for __getitem__, __setitem__ instead of dict?
    if isinstance(out, dict):
        out[key] = out.get(key, 0) + 1
        return out
    setattr(out, key, getattr(out, key) + 1)
    return out


def clear_collab_counts(out):
    set_ex(out, 'is_exposed_outside', False)
    set_ex(out, 'is_exposed_public', False)
    set_ex(out, 'is_exposed_everyone', False)
    set_ex(out, 'count_insiders', 0)
    set_ex(out, 'count_outsiders', 0)


def count_collab(out, docstr=None, collab=None, user=None, mydomains=None):
    """For any source, do counting logic onto object 'out'.
    docstr = default: or domain:$domain or user:$user@$domain
    collab = {'type': , 'value': , 'public': ,...}
    user = $user@$domain
    mydomains 

    Free bonus, return the parsed parts of the docstr as a dict:
    {'type': (user|group|default|domain),
    ['domain': domain,]
    ['user': user|group,]
    ['value': user|group @ domain,]  # consitent with collab dicts
    }
    One could pass this to annotate_collab_entry.
    """

    def _set_for_user(value):
        """Return (user, domain) or ('unknown user', None)"""
        if '@' not in value:
            if value.lower() == 'unknown user':
                pass
#                logging.warn('bogus collab user "%s", no @domain', value)
            else:
                logging.error('bogus collab user "%s", no @domain', value)
            return (value, None)
        user, actual_domain = value.split('@', 1)
        if actual_domain in mydomains:
            inc_ex(out, 'count_insiders')
        else:
            set_ex(out, 'is_exposed_outside')
            inc_ex(out, 'count_outsiders')
        return (user, actual_domain)
    def _set_for_type_value(t, value):
        if t == 'domain':
            if value in mydomains:
                set_ex(out, 'is_exposed_everyone')
                #set_ex(out, 'is_exposed_outside', False)
            else:
                set_ex(out, 'is_exposed_outside')
                inc_ex(out, 'count_outsiders')
            return {'type':t, 'domain':value}
        elif (t == 'user') or (t == 'group'):
            user, actual_domain = _set_for_user(value)
            return {'type':t, 'user':user, 'domain':actual_domain, 'value': value}
        else:
            logging.error('unknown sharing type "%s" = "%s"', t, value)
            return None
    if docstr:
        if ':' not in docstr:
            logging.error('bogus collab str "%s"', docstr)
            return None
        if docstr == 'default:':
            set_ex(out, 'is_exposed_public')
            return {'type': 'default'}
        t, value = docstr.split(':', 1)
        return _set_for_type_value(t, value)
    elif collab:
        if collab.get('public'):
            set_ex(out, 'is_exposed_public')
            return
        return _set_for_type_value(collab['type'], collab['value'])
    elif user:
        user, actual_domain = _set_for_user(user)
        return {'type':user, 'user':user, 'domain':actual_domain, 'value': user}
    else:
        logging.error('bogus invocation of count_collab')
    return None
