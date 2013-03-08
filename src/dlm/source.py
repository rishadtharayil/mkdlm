#!/usr/bin/env python
'''
Copyright (C) 2011-2013  MKay

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

"""The source-module contains the Source-class.

The Source-class represents a source of a download where the file can be
loaded from.
"""

from cookielib import Cookie
from re import match
from threading import Lock
from time import time
from urlparse import urlparse

from event.eventlistener import EventListener


class Source:
    """A Source-object contains information on a source of a download.

    This includes the location of the downloadable file as a URL as well
    as information about handling the source. For example how many
    redirects should be allowed (when using http) or how many retries
    on errors should be allowed and how much time should be waited
    between retries.
    The Source-object may also contain the filesize, filename and real
    url (the url after following redirects) if these information was
    loaded by a slot.InfoSlot.

    Public instance variables:
    original_url -- the url that was used to create the Source
    url -- the real url (after following redirects)
    max_redirects -- the maximum number of redirects. A negative value
                     means infinity.
    max_retries -- the maximum number of retries on errors. A negative
                   value means infinity.
    wait_time -- the time in seconds to wait between retries on errors
    filename -- the filename of the Source. It is simply extracted from
                the URL and may be changed by a slot.InfoSlot.
    filesize -- the filesize may be set by an InfoSlot or is None.
    retries -- the current number of retries
    user_agent --
    referrer --
    cookies --
    timeout --
    valid --

    url_changed_event -- An event.eventlistener.EventListener object.
                         The event is signalled when the url has
                         changed. The listener accepts the Source as
                         parameter.
    retries_changed_event -- An event.eventlistener.EventListener object
                             The event is signalled when the number of
                             retries or the max. number of retries has
                             changed. The listener accepts the Source as
                             parameter.
    """

    @staticmethod
    def is_cookie_string_valid(cookie_string):
        regex = r'^[^;=]+=[^;=]+(;[^;=]+=[^;=]+)*$'
        return match(regex, cookie_string) is not None

    def __init__(self, url, max_redirects, max_retries, wait_time):
        """Initialize the Source-object.

        url -- the url from which the file can be loaded
        max_redirects -- the maximum number of redirects. A negative
                         value means infinity.
        max_retries -- the maximum number of retries on errors. A
                       negative value means infinity.
        wait_time -- the time in seconds to wait between retries on
                     errors
        """
        self.url_changed_event = EventListener()
        self.retries_changed_event = EventListener()

        self.original_url = url
        self.set_url(url)
        self.max_redirects = max_redirects
        self.set_max_retries(max_retries)
        self.wait_time = wait_time
        self.filename = urlparse(url).path.split('/').pop().strip()
        if self.filename == '':
            self.filename = 'UnknownFileName'
        self.filesize = None
        self.retries = 0
        self.timeout = 5
        self.user_agent = ''
        self.referrer = ''

        self.cookie_string = ''
        self.cookies = []
        self.cookie_objects = None

        self.valid = True
        # TODO: better use monotonic time
        # contains timestamps which each specify when retry is allowed
        self._failed = []
        self._retry_lock = Lock()

        # Active slots are slots, which started receiving data and are
        # still loading.
        # Running slots are slots, which have started using the source.
        # They max have requested a chunk from the source but maybe not
        # received any data.
        self._running_slot_lock = Lock()
        self.running_slots = 0

        self._active_slot_lock = Lock()
        self.active_slots = 0
        self.max_active_slots = 0
        self.max_slots_determined = False

    @staticmethod
    def create_from_dict(dict):
        # TODO: validate values?!
        source = Source(dict['original_url'], dict['max_redirects'], dict['max_retries'], dict['wait_time'])
        source.url = dict['url']
        source.filename = dict['filename']
        source.filesize = dict['filesize']
        source.retries = dict['retries']
        source.timeout = dict['timeout']
        source.user_agent = dict['user_agent']
        source.referrer = dict['referrer']
        source.valid = dict['valid']
        source.max_active_slots = dict['max_active_slots']
        source.max_slots_determined = dict['max_slots_determined']
        
        source.set_cookie_string(dict['cookie_string'])
        
        if 'cookies' in dict and dict['cookies'] is not None:
            source.cookie_objects = []
            for cookie in dict['cookies']:
                c = Cookie(cookie['version'],
                        cookie['name'],
                        cookie['value'],
                        cookie['port'],
                        cookie['port_specified'],
                        cookie['domain'],
                        cookie['domain_specified'],
                        cookie['domain_initial_dot'],
                        cookie['path'],
                        cookie['path_specified'],
                        cookie['secure'],
                        cookie['expires'],
                        cookie['discard'],
                        cookie['comment'],
                        cookie['comment_url'],
                        {},
                        cookie['rfc2109']
                    )
                source.cookie_objects.append(c)
        
        return source

    def get_as_dict(self):
        cookieList = []
        if self.cookie_objects is not None:
            for cookie in self.cookie_objects:
                cookieList.append({
                    'version': cookie.version,
                    'name': cookie.name,
                    'value': cookie.value,
                    'port': cookie.port,
                    'port_specified': cookie.port_specified,
                    'domain': cookie.domain,
                    'domain_specified': cookie.domain_specified,
                    'domain_initial_dot': cookie.domain_initial_dot,
                    'path': cookie.path,
                    'path_specified': cookie.path_specified,
                    'secure': cookie.secure,
                    'expires': cookie.expires,
                    'discard': cookie.discard,
                    'comment': cookie.comment,
                    'comment_url': cookie.comment_url,
                    'rfc2109': cookie.rfc2109
                })
        
        if not cookieList:
            cookieList = None

        source = {
            'original_url': self.original_url,
            'url': self.url,
            'max_redirects': self.max_redirects,
            'max_retries': self.max_retries,
            'wait_time': self.wait_time,
            'filename': self.filename,
            'filesize': self.filesize,
            'retries': self.retries,
            'timeout': self.timeout,
            'user_agent': self.user_agent,
            'referrer': self.referrer,
            'valid': self.valid,
            'max_active_slots': self.max_active_slots,
            'max_slots_determined': self.max_slots_determined,
            'cookie_string': self.cookie_string,
            'cookies': cookieList
        }
        return source

    def set_cookie_string(self, cookie_string):
        if Source.is_cookie_string_valid(cookie_string):
            self.cookie_string = cookie_string
            tmp = []
            cookies = cookie_string.split(';')
            for cookie in cookies:
                cookie_data = cookie.split('=')
                tmp.append((cookie_data[0], cookie_data[1]))
            self.cookies = tmp

    def set_url(self, url):
        """Change the URL of this Source.

        url_changed_event will be signalled.

        url -- the new url
        """
        self.url = url
        self.url_changed_event.signal(self)

    def set_max_retries(self, max_retries):
        self.max_retries = max_retries
        self.retries_changed_event.signal(self)

    def inc_active_slots(self, decrement=False):
        with self._active_slot_lock:
            if decrement:
                self.active_slots -= 1
            else:
                self.active_slots += 1
                if self.active_slots > self.max_active_slots:
                    self.max_active_slots = self.active_slots

    def inc_running_slots(self, decrement=False):
        with self._running_slot_lock:
            if decrement:
                self.running_slots -= 1
            else:
                self.running_slots += 1

    def add_fail(self, data_received):
        """Tell the source, that an error occurred while using the
        Source.

        For example the connection to the Source-Server timed out or the
        file does not exist etc.. The next slot using this source may
        wait some time before retrying.
        """
        # If there was a slot loading using this source at any time
        # then self.max_active_slots is the max. number of parallel
        # slots if another slot failed before receiving any data.
        # E.g. if two slots are loading (self.max_active_slots == 2) and
        # the next slot recevied a http-403-error. Then only 2 parallel
        # slots using this source are allowed.
        if self.max_active_slots > 0 and not data_received:
            self.max_slots_determined = True

        with self._retry_lock:
            # the next slot needs to wait before retrying
            self._failed.append(time() + self.wait_time)

    def is_retry_allowed(self):
        """Checks if its allowed to use this Source to load data.

        If no error has occurred before, the value 0 is returned
        indicating that everything is fine and the Source can be used to
        load data.
        If an error has occurred before, it checks if max_retries is
        reached. If max_retries is reached, the value -1 is returned
        indicating that this Source should not be used to load data. If
        max_retries is not reached, the Source can be used to load data
        but the Slot should wait some seconds. The time until the slot
        should wait is returned.
        """
        ret = 0  # allowed, no retry
        retries_changed = False
        with self._retry_lock:
            if len(self._failed) > 0 and (self.retries < self.max_retries or
                    self.max_retries < 0):
                retries_changed = True
                self.retries += 1
                ret = self._failed.pop(0)
            elif len(self._failed) > 0:
                # reached max retries
                ret = -1

        if retries_changed:
            self.retries_changed_event.signal(self)
        return ret
