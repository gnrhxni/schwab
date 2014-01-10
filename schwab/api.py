
import re
import csv
import json
import logging
import collections
from StringIO import StringIO

log = logging.getLogger(__name__)

import requests
from bs4 import BeautifulSoup

_default_api = None

BASE = 'https://client.schwab.com'

DEFAULT_SESSION_PATH = "./session.json"
MAX_REAUTH_ATTEMPTS = 1

class AuthError(KeyError):
    pass

class StaleSession(IOError):
    pass


def load(location = DEFAULT_SESSION_PATH):
    with open(location, 'rb') as fp:
        session_dict = json.load(fp)

    if 'auth' in session_dict and session_dict['auth']:
        session_dict['auth'] = tuple(session_dict['auth'])

    if 'cookies' in session_dict:
        session_dict['cookies'] = requests.utils.cookiejar_from_dict(
            session_dict['cookies'] )

    session = requests.session()
    for key, val in session_dict.iteritems():
        setattr(session, key, val)

    api = Api(session=session)
    if api.ping():
        return api


class Api(object):
    
    def __init__(self, username=None, password=None, 
                       session=None,  persistent=True):
        self.username   = username
        self.password   = password
        self.session    = session
        self.persistent = persistent

        if not session:
            self.session = self._authenticate(username, password)

        self._accounts = None
        self._current_acct = None

        global _default_api
        _default_api = self


    @property
    def accounts(self):
        if self._accounts is None:
            self._accounts = self._refresh_accounts()
        return self._accounts
        

    def _refresh_accounts(self):
        dom = BeautifulSoup( 
            self.request('POST',
                         '/Areas'
                         '/MvcGlobal'
                         '/AccountSelectorListJson.ashx',
                         data={'val': 'NYYYNNNNNNNNNN'}).text
        )

        accounts = list()
        tags  = dom.find_all('span', re.compile(r'account-'))
        for i, tag in enumerate(tags):
            if i % 2 == 0:
                name = tag.text.strip()
            else:
                number = tag.text.strip()
                accounts.append((name, number))

        return [ Account(name, number) for name, number in accounts ]


    @property
    def _current_account(self):
        """Return the current account. """
        return self._current_acct

    @_current_account.setter
    def _current_account(self, number):
        if self._current_acct != number:
            logging.debug("Updating current account on Schwab remote")
            self.request('POST', '/Areas/MvcGlobal/SwitchAccountJson.ashx',
                         data={ 'hdnSA': 'S|%s|2|N'%(number) })
            self._current_acct = number


    def authenticate(self, username=None, password=None):
        username = self.username if not username else username
        password = self.password if not password else password
        self.session = self._authenticate(username, password)


    def request(self, method, url, **kwargs):
        n_tries = kwargs.pop('request_attempts', 0)

        response = self.session.request(method, BASE+url, **kwargs)

        if 'SessionTimeOut=Y' in response.url:
            if n_tries <= MAX_REAUTH_ATTEMPTS:
                log.debug("Stale session. Reauthenticating. Tries: %d", 
                          n_tries)
                n_tries += 1
                self.authenticate()
                return self.request(method, BASE+url, 
                                    request_attempts=n_tries, **kwargs)
            else:
                raise StaleSession("Tried too many times to reauth")

        return response


    def ping(self):
        response = self.request('GET', 
                                '/Areas'
                                '/MvcGlobal'
                                '/AccountSelectorListJson.ashx')
        return response.status_code == requests.codes.ok
            

    def _authenticate(self, username, password):
        log.debug('Authenticating')

        if not username or not password:
            raise AuthError("Both username and password are"
                            " required to authenticate")

        s = requests.Session()
        s.headers.update({
                'User-Agent': ("Mozilla/5.0 (Macintosh; Intel Mac "
                               "OS X 10_8_5) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) "
                               "Chrome/30.0.1599.69 Safari/537.36")
        })
        r = s.post(BASE+'/Login/SignOn/SignOn.ashx',
                   data={'SignonAccountNumber' : username,
                         'SignonPassword'      : password,})
        if r.status_code == requests.codes.ok and 'Summary.' in r.url:
            self.save()
            return s
        else:
            if not r.status_code == requests.codes.ok:
                r.raise_for_status()
            else:
                raise AuthError('Bad username or password')


    def save(self, location = DEFAULT_SESSION_PATH):
        log.debug("Saving session state to location %s", location)
        attrs = ['headers', 'cookies', 'auth', 'timeout', 'proxies', 'params',
                 'config', 'verify']
        
        session_dict = dict()
        
        for attr in attrs:
            if hasattr(self.session, attr):
                if attr == "cookies":
                    val = requests.utils.dict_from_cookiejar(
                        self.session.cookies)
                elif attr == "headers":
                    val = dict(self.session.headers)
                else:
                    val = getattr(self.session, attr)
                session_dict[attr] = val 
            
        with open(location, 'wb') as fp:
            json.dump(session_dict, fp)


    def __del__(self):
        if self.persistent:
            self.save()


class Account(object):
    
    def __init__(self, name, number, api=None):
        self.name   = name
        self.number = number

        if api is None:
            api = _default_api
        self.api = api

        self._transactions = list()

    @property
    def transactions(self, page=0):
        if len(self.number) == 9:
            return self._get_brokerage_txs(page=page)
        else:
            return self._get_bank_txs(page=page)

    
    def _get_brokerage_txs(self, page=0):
        raise Exception("Sorry, retrieving brokerage transactions"
                        " isn't supported yet.")

    def _get_bank_txs(self, page=0):
        self.api._current_account = self.number
        # Bounce over here first
        dom = BeautifulSoup(
            self.api.request(
                'GET', '/Accounts/History/BankHistory.aspx'
            ).text
        )
        form_bits = dict( (tag.attrs['name'], tag.attrs['value']) 
                          for tag in dom.find_all('input', type='hidden')
                          if 'name' in tag.attrs and 'value' in tag.attrs )
        form_bits['hdnExport'] = 'Export'
        form_bits['__EVENTTARGET'] = ''
        form_bits['__EVENTARGUMENT'] = ''

        response = self.api.request( 
            'POST', '/Accounts/History/BankHistory.aspx',
            data=form_bits
        )
        
        regex = re.compile(r'\d+/\d+/\d+')
        return [ 
            Transaction(*fields) 
            for fields in csv.reader(StringIO(response.text))
            if regex.match(fields[0])
        ]
        
Transaction = collections.namedtuple(
    "Transaction", 
    ['date', 'type', 'checknum', 
     'description',  'withdrawal',
     'deposit',      'runningbalance'])
