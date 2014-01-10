#!/usr/bin/env python

import re
import sys
import csv
import json
import logging
import optparse
import datetime
from getpass import getpass as _getpass

import dateutil.parser
dparse = dateutil.parser.parse

from . import (
    api
)


logging.basicConfig(format="[%(levelname)s | %(name)s]: %(message)s")
log = logging.getLogger(__name__)


HELP = """Schwab command line tool
Usage: %s <command> [arguments] [options]
"""

# name: (default, documentation)
GLOBAL_OPTIONS = { 
    'session': ('session.json', 
                "Where to save session state"),
    'logging': ('WARNING',
                "Set logging verbosity. Values: debug, info, warning, error"),
}


def _get_option(local_options, key, global_options=GLOBAL_OPTIONS):
    if key in local_options:
        val = local_options[key]
    else:
        val =  global_options.get(key, False)
        if val:
            val = val[0]

    return val


def _print_usage(quit_with_status=1):
    print HELP
    print "Available commands:"
    g = globals().copy()
    for name, item in g.iteritems():
        if type(item) is type( lambda : None )\
           and not name.startswith('_')\
           and not name == "main":
            print "%-10s\t%s" %(item.func_name.strip(), 
                               item.func_doc.strip())
            print
    print

    print "Options common to all commands:"
    for name, value in GLOBAL_OPTIONS.iteritems():
        default, doc = value
        if type(default) is bool:
            print "-%s\t%s" %(name, doc)
        else:
            print "--%s\tDefault: %s - %s" %(name, default, doc)

    if quit_with_status:
        sys.exit(quit_with_status)
                

def _get_api(opts_dict):
    session = _get_option(opts_dict, "session")
    try:
        return api.load(session)
    except (IOError, ValueError, api.AuthError) as e:
        logging.debug("loading session failed: %s", e)
        logging.debug("I'll ask instead")
        user = _get_option(opts_dict, 'username')
        if not user:
            user   = raw_input('Username: ')

        passwd = _getpass()
        
        return api.Api(user, passwd)


def ping(args, opts):

    """ See if schwab is accessible
    """
    try:
        ok = _get_api(opts).ping()
    except Exception as e:
        ok = False
        logging.exception(e)

    if not ok:
        print "Schwab is somehow not open for business"
        return 1
    else:
        print "Schwab is open for business"
        return 0


def accounts(args, opts):
    """ Show account information
        Usage:   accounts [options]
        Options: --format <json | csv | human>
    """

    fmt = opts.get('format', 'human')

    schwab = _get_api(opts)
    accounts = schwab.accounts

    if fmt == 'csv':
        for account in accounts:
            print ",".join(account)
    elif fmt == 'json':
        json.dumps({"Accounts": accounts})
    else:
        print "Available Accounts:"
        for account in accounts:
            print '\t%s ( %s )' %(account.name, account.number)

    return 0


def transactions(args, opts):
    """ Print transactions for an account
        Usage:   transactions <Account Name | Account Number>
        Options: --format <json | csv | human | tsv>  Default: Human
                 --from <date / time>                 Default: 1 month ago
                 --to <date / time>                   Default: today
    """

    name      = args[0]
    fmt       = opts.get('format', 'human')
    from_date = dparse( opts.get('from', '1 month ago'), fuzzy=True )
    to_date   = dparse( opts.get('to', 'today'), fuzzy=True )

    schwab = _get_api(opts)
    account = None
    for acct in schwab.accounts:
        if name.lower() in acct.name.lower() \
           or name.lower() in acct.number.lower():
            account = acct
            break

    transactions = [ t for t in account.transactions
                     if to_date > dparse(t.date) > from_date ]

    if fmt == "json":
        print json.dumps({'transactions': list(transactions) })
    elif fmt == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(transactions[0]._fields)
        for tx in transactions:
            writer.writerow(tx)
    else:
        print "\t".join(transactions[0]._fields)
        for tx in transactions:
            print "\t".join(tx)

    return 0


def main():
    opts = dict()
    args = list()

    if '-h' in sys.argv or '--help' in sys.argv \
            or len(sys.argv) < 2:
        _print_usage(quit_with_status=1)

    in_opt  = False
    the_opt = str()
    for val in sys.argv[1:]:
        # capture options but not -
        # which is interpreted as stdin
        if re.match(r'^--?.+$', val):
            num_dashes = val.count('-')
            val = val[num_dashes:]

            in_opt = True if num_dashes == 2 else False
            opts[val] = None
            the_opt = val

            continue

        if val == '-':
            val = sys.stdin

        if in_opt:
            opts[the_opt] = val
        else:
            args.append(val)
        
        in_opt = False

    funcname = args[0]
    del( args[0] )
    func = globals()[funcname]

    logging.getLogger().setLevel(
        getattr(logging, _get_option(opts, 'logging').upper())
    )

    try:
        exit_status = func(args, opts)
    except KeyboardInterrupt:
        print "Ouch!"
        sys.exit()

    sys.exit(exit_status)


if __name__ == '__main__':
    main()
