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

"""This module contains classes to load files from servers via http/ftp.

The user can use the Connection-class to fetch information or data from
a server specified by the url in a Source-object.
"""

from urllib2 import HTTPRedirectHandler, HTTPError, URLError, Request, \
                    build_opener, FTPHandler, HTTPCookieProcessor
from urlparse import urlparse
from urllib import splitport, splituser, splitpasswd, splitattr, unquote, \
                    addclosehook, addinfourl
import urllib
import ftplib
import socket
import sys
import mimetypes
import mimetools

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from event.eventlistener import EventListener


class _LimitedHTTPRedirectHandler(HTTPRedirectHandler):
    """This class is used to limit the number of redirects."""
    def __init__(self, c):
        """Initialize

        c -- the maximum number of redirects
        """
        self._counter = 0
        self._maxRedirects = c

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        self._counter += 1
        if (self._counter > self._maxRedirects):
            raise HTTPError(req.get_full_url(), code,
                        'Reached the maximum number of redirects', hdrs, fp)
        else:
            # TODO: really reuse referer-header?
            return HTTPRedirectHandler.redirect_request(self, req, fp, code,
                                                        msg, hdrs, newurl)



class FTPChunkHandler(FTPHandler):
    """The code was taken from urllib2.py.

    The only difference is that offsets are supported by this class
    using the REST-command. Offsets are needed for chunked loading.
    """

    def ftp_open(self, req):
        import mimetypes
        host = req.get_host()
        if not host:
            raise URLError('ftp error: no host given')
        host, port = splitport(host)
        if port is None:
            port = ftplib.FTP_PORT
        else:
            port = int(port)

        # username/password handling
        user, host = splituser(host)
        if user:
            user, passwd = splitpasswd(user)
        else:
            passwd = None
        host = unquote(host)
        user = unquote(user or '')
        passwd = unquote(passwd or '')

        try:
            host = socket.gethostbyname(host)
        except socket.error, msg:
            raise URLError(msg)
        path, attrs = splitattr(req.get_selector())
        dirs = path.split('/')
        dirs = map(unquote, dirs)
        dirs, file = dirs[:-1], dirs[-1]
        if dirs and not dirs[0]:
            dirs = dirs[1:]
        try:
            fw = self.connect_ftp(user, passwd, host, port, dirs, req.timeout)
            type = file and 'I' or 'D'
            for attr in attrs:
                attr, value = splitvalue(attr)
                if attr.lower() == 'type' and \
                   value in ('a', 'A', 'i', 'I', 'd', 'D'):
                    type = value.upper()

            # EDIT START
            # get REST (file offset) from headers
            rest = 0
            offset = req.headers.get('Offset', None)
            if offset is not None and offset > 0:
                rest = offset
            # EDIT END

            fp, retrlen = fw.retrfile(file, type, rest)
            headers = ""
            mtype = mimetypes.guess_type(req.get_full_url())[0]
            if mtype:
                headers += "Content-type: %s\n" % mtype
            if retrlen is not None and retrlen >= 0:
                headers += "Content-length: %d\n" % retrlen
            sf = StringIO(headers)
            headers = mimetools.Message(sf)
            return addinfourl(fp, headers, req.get_full_url())
        except ftplib.all_errors, msg:
            raise URLError, ('ftp error: %s' % msg), sys.exc_info()[2]

    def connect_ftp(self, user, passwd, host, port, dirs, timeout):
        fw = ftpwrapper(user, passwd, host, port, dirs, timeout)
##        fw.ftp.set_debuglevel(1)
        return fw


class ftpwrapper(urllib.ftpwrapper):
    """Class used by open_ftp() for caching open FTP connections.

    The code was taken from urllib.py.
    The only difference is that offsets are supported by this class
    using the REST-command.
    """

    def retrfile(self, file, type, rest=None):
        self.endtransfer()
        if type in ('d', 'D'): cmd = 'TYPE A'; isdir = 1
        else: cmd = 'TYPE ' + type; isdir = 0
        try:
            self.ftp.voidcmd(cmd)
        except ftplib.all_errors:
            self.init()
            self.ftp.voidcmd(cmd)
        conn = None
        if file and not isdir:
            # Try to retrieve as a file
            try:
                cmd = 'RETR ' + file
                # EDIT START
                conn = self.ftp.ntransfercmd(cmd, rest)
                # EDIT END
            except ftplib.error_perm, reason:
                if str(reason)[:3] != '550':
                    raise IOError, ('ftp error', reason), sys.exc_info()[2]
        if not conn:
            # Set transfer mode to ASCII!
            self.ftp.voidcmd('TYPE A')
            # Try a directory listing. Verify that directory exists.
            if file:
                pwd = self.ftp.pwd()
                try:
                    try:
                        self.ftp.cwd(file)
                    except ftplib.error_perm, reason:
                        raise IOError, ('ftp error', reason), sys.exc_info()[2]
                finally:
                    self.ftp.cwd(pwd)
                cmd = 'LIST ' + file
            else:
                cmd = 'LIST'
            conn = self.ftp.ntransfercmd(cmd)
        self.busy = 1
        # Pass back both a suitably decorated object and a retrieval length
        return (addclosehook(conn[0].makefile('rb'),
                             self.endtransfer), conn[1])



class FakeCookieResponse:
    def __init__(self, cookies, url=None):
        cookie_hdrs = []
        for (name, value) in cookies:
            cookie_hdrs.append('set-cookie: {0}={1}'.format(name, value))
        f = StringIO('\n'.join(cookie_hdrs))
        self._headers = mimetools.Message(f)
        self._url = url

    def info(self):
        return self._headers


class Connection:
    """A Connection-object is used to fetch information (like the file
    size) from a Source or load data from a Source.

    Public instance variables:
    source -- the source to use
    url -- the url used for the request
    url_parts -- the parts of the url as dict

    data_received_event -- An event.eventlistener.EventListener object.
                           The event is signalled when data is received.
                           Each listener will be called only once when
                           data was received. The listeners are called
                           without arguments.
    """

    def __init__(self, source):
        """Initialize

        source -- the Source that will be used by the Connection
        """
        self.source = source
        self.url = source.url
        self.url_parts = urlparse(self.url)
        self.data_received_event = EventListener()
        self._signaled_data_received = False
        self._response = None

    def _signal_data_received(self):
        """Signal data_received_event if not already done."""
        if self._signaled_data_received:
            return
        self.data_received_event.signal()
        self._signaled_data_received = True

    def fetch_infos(self):
        """Fetch the information (like filename, size).

        The connection will NOT be closed automatically!
        """
        real_url, filename, filesize = self._request_infos()
        if filename is None:
            # extract filename from url
            url_filename = urlparse(real_url).path.split('/').pop().strip()
            if url_filename != '':
                filename = url_filename
        return (real_url, filename, filesize)


    def fetch_data(self, chunk, target_file, download):
        """Fetch the data.

        The connection will be closed automatically!

        chunk -- it specifies which range of data should be fetched
        target_file -- the TargetFile-object which is used to store the
                       data on disk
        download -- the Download-object holding this connection
        """
        self._request_data(chunk, target_file, download)

    def close(self):
        """Close the connection."""
        if self._response is not None:
            self._response.close()

    def _request(self, chunk=None, info_request=False):
        """Do the request.

        Used for fetching information and for fetching data.

        chunk -- specifies which range (part) should be loaded.
        info_request -- specifies if only information should be fetched.
        """
        if self._response is not None:
            return self._response

        if self.url_parts.scheme == 'http':
            max_redirects = 0
            if info_request:
                # allow redirects only for info-requests
                max_redirects = self.source.max_redirects
            req = Request(self.url)

            cookie_processor = HTTPCookieProcessor()

            if self.source.cookie_objects is not None:
                # Use the cookies which were received by previous
                # (info-)requests.
                for cookie in self.source.cookie_objects:
                    cookie_processor.cookiejar.set_cookie(cookie)
            elif len(self.source.cookies) > 0 and info_request:
                # This is the first (info-)request where cookies are
                # used. Use user-defined cookies.
                fcres = FakeCookieResponse(self.source.cookies, self.url)
                cookie_processor.cookiejar.extract_cookies(fcres, req)

            if self.source.referrer != '':
                req.add_header('Referer', self.source.referrer)
            if self.source.user_agent != '':
                req.add_header('User-Agent', self.source.user_agent)

            if chunk is not None:
                start_offset = chunk.offset + chunk.loaded
                req.add_header('Range', 'bytes=' + str(start_offset) + '-')

            opener = build_opener(_LimitedHTTPRedirectHandler(max_redirects),
                                    cookie_processor)
            self._response = opener.open(req, timeout=self.source.timeout)

            if self.source.cookie_objects is None:
                # save cookie objects for later use (e.g. DataSlots)
                cookie_objects = []
                for cookie in cookie_processor.cookiejar:
                    cookie_objects.append(cookie)
                self.source.cookie_objects = cookie_objects

            return self._response

        elif self.url_parts.scheme == 'ftp':
            req = Request(self.url)
            if chunk is not None:
                start_offset = chunk.offset + chunk.loaded
                req.add_header('Offset', str(start_offset))
            opener = build_opener(FTPChunkHandler())
            self._response = opener.open(req, timeout=self.source.timeout)
            return self._response
        else:
            raise URLError('The protocol is not supported.')


    def _request_infos(self):
        """Fetch the information (like filename, size) using _request.

        The connection will NOT be closed automatically!
        """
        response = self._request(info_request=True)

        if self.url_parts.scheme == 'http':
            headers = response.info()
            real_url = response.geturl()
            filename = None
            filesize = None

            # get filename from header
            if 'content-disposition' in headers:
                tmp = headers['content-disposition'].split('filename=')
                if len(tmp) == 2:
                    tmp = tmp[1].split(';')
                    tmp = tmp[0].strip(' "')
                    if tmp != '':
                        filename = tmp

            # get filesize from header
            if 'content-length' in headers:
                filesize = long(headers['content-length'].strip())

            return (real_url, filename, filesize)

        elif self.url_parts.scheme == 'ftp':
            headers = response.info()
            real_url = response.geturl()

            # get filesize from header
            filesize = None
            if 'content-length' in headers:
                filesize = long(headers['content-length'].strip())

            return (real_url, None, filesize)

        else:
            return (None, None, None)


    def _request_data(self, chunk, target_file, download):
        """Fetch the data using _request.

        The connection will be closed automatically!

        chunk -- it specifies which range of data should be fetched
        target_file -- the TargetFile-object which is used to store the
                       data on disk
        download -- the Download-object holding this connection
        """
        response = None
        try:
            response = self._request(chunk=chunk)
        except Exception, e:
            self.close()
            raise e

        try:
            if self.url_parts.scheme == 'http':
                headers = response.info()

                if (not('content-range' in headers) and (chunk.offset != 0 or
                    chunk.loaded != 0)):
                    # server has not responded with required partial data
                    # TODO: The source does not support slots. (Already handled?!)
                    raise URLError('The server does not support partial/' +
                                    'resume downloads.')

            # download is not paused/failed/finished/...
            # there are still bytes which need to be loaded.
            while (download.is_loading() and
                   not chunk.is_finished(download.slots_supported)):
                # TODO: Speed Limit !!
                to_load = chunk.bytes_left(download.slots_supported)
                if to_load is None or to_load > 4096:
                    to_load = 4096
                elif to_load <= 0:
                    break
                data = response.read(to_load)
                if data == '':
                    break
                self._signal_data_received()
                file_offset = chunk.offset + chunk.loaded
                target_file.write(file_offset, data)
                chunk.loaded += len(data)

            if (not download.is_loading() and
                    not chunk.is_finished(download.slots_supported)):
                # e.g. download was paused. it's ok that chunk is not finished
                raise ChunkNotFinishedError(critical=False,
                            reason='Chunk not finished. Download was stopped.')

            elif (chunk.length is not None and
                    not chunk.is_finished(download.slots_supported)):
                # we did not received all data ... connection closed?
                # this is a failure!
                raise ChunkNotFinishedError(critical=True,
                            reason='Chunk not finished.')

        finally:
            self.close()
            from time import sleep
            sleep(1)  # wait while connection is being closed
            # TODO: Any chance to force close connection to avoid
            #       waiting a "random" time?
            #       We need to know that connection is closed, because
            #       source may support only a limited number of
            #       connections. Before starting a new slot/connection
            #       we should know that the previous connection is
            #       closed.
            #       See http://stackoverflow.com/questions/5442291/close-urllib2-connection



class ChunkNotFinishedError(URLError):
    def __init__(self, critical, reason):
        self.critical = critical
        URLError.__init__(self, reason)
