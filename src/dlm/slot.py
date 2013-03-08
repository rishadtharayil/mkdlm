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

"""The slot-module contains the two classes InfoSlot and DataSlot.

An InfoSlot is a slot, that can be used to get information about the
download, for example filename and size.

The DataSlot then can be used to download the file.
"""

from threading import Thread
from urllib2 import URLError, HTTPError
from time import time, sleep
from Queue import Empty

from connection import Connection, ChunkNotFinishedError
from event.eventlistener import EventListener
from log import Log, MessageType
from targetfile import TargetFileIOError


class InfoSlot(Thread):
    """The InfoSlot is a subclass of threading.Thread and can be used to
    load the information of a download or more precisely a Source-object
    like filename and size etc..

    The new information (url, filename, filesize) will be automatically
    set in the Source-object.

    Public instance variables:
    connection -- the connection used to fetch the information. The
                  connection can later be used for a DataSlot to load
                  data because it is not closed automatically.
    """

    def __init__(self, name, source, download, success_clb, fail_clb):
        """Initialize the InfoSlot-object.

        name -- the name of the slot. It is used as thread-name and when
                logging messages.
        source -- the source to fetch the information from
        download -- the download holding this slot
        success_clb -- a parameter less function that will be called
                       after the information were successfully fetched.
        fail_clb -- a parameter less function that will be called after
                    fetching information (and all retries) has failed.
        """
        self._source = source
        self._download = download
        if self._download is None:
            self.log = Log()
        else:
            self.log = download.log
        self._success_clb = success_clb
        self._fail_clb = fail_clb
        self.connection = None
        Thread.__init__(self, name=name)

    def run(self):
        """Called when the slot-thread is started.

        The information will be fetched using a Connection-object.
        The slot will automatically retry/wait on errors and call the
        appropriate callback-methods.

        NOTE: The connection will NOT be closed automatically.
        """
        real_url, filename, filesize = None, None, None
        success = False
        retry = True

        while retry:
            # Download may be paused --> stop fetching infos
            if (self._download is not None and
                    not self._download.is_fetching_info()):
                return

            # maybe we need to wait some seconds between retries
            wait_until = self._source.is_retry_allowed()
            if wait_until < 0:
                retry = False
                continue
            elif wait_until > 0 and wait_until - time() > 0:
                self.log.add_log_entry(MessageType.info, self.getName(),
                        'Retry in {0} seconds!'.format(wait_until - time()))
                # wait until retry, but still check if state has changed
                while time() < wait_until:
                    sleep(0.2)
                    if (self._download is not None and not
                            self._download.is_fetching_info()):
                        return

            # Download may be paused --> stop fetching infos
            #if not self._download.is_fetching_info():
            #    return

            c = self.connection = Connection(self._source)
            try:
                real_url, filename, filesize = c.fetch_infos()
                retry = False
                success = True
            except HTTPError, e:
                self._source.add_fail(False)
                self.log.add_log_entry(MessageType.error, self.getName(),
                                        'HTTP-Error: ' + str(e))
            except URLError, e:
                self._source.add_fail(False)
                self.log.add_log_entry(MessageType.error, self.getName(),
                                        'Error: ' + str(e.reason))
            except IOError, e:
                self._source.add_fail(False)
                self.log.add_log_entry(MessageType.error, self.getName(),
                                        'IOError: ' + str(e))

        if success:
            self._source.set_url(real_url)
            if filename is not None:
                self._source.filename = filename
            if filesize is not None:
                self._source.filesize = filesize
            self._success_clb()
        else:
            self._fail_clb()



class DataSlot(Thread):
    """The DataSlot is a subclass of threading.Thread and can be used to
    load the data of a download.

    The download will be informed about events using listeners, e.g. when
    a chunk starts loading or a chunk was failed/finished.

    Public instance variables:
    connection -- the connection used to load the data. Note that it will
                  be closed automatically.

    chunk_started_event  -- An event.eventlistener.EventListener object.
                            The event is signalled when some data of a
                            chunk was received. The listener is called
                            with the chunk as parameter.
    chunk_finished_event -- An event.eventlistener.EventListener object.
                            The event is signalled when all data of a
                            chunk was received. The listener is called
                            without one parameter indicating if some
                            data has been loaded or not.
    chunk_failed_event   -- An event.eventlistener.EventListener object.
                            The event is signalled if receiving data of
                            a chunk failed. The listener is called with
                            three parameters.
                            The first parameter is the failed chunk. The
                            second parameter is a boolean value
                            indicating if the error was an file-ioerror
                            or not. The third parameter is a boolean
                            indicating if some data has been loaded or
                            not.
    """

    def __init__(self, name, download, target_file,
                 chunk=None, connection=None):
        """Initialize the DataSlot-object.

        name -- the name of the slot. It is used as thread-name and when
                logging messages.
        download -- the download holding this slot
        target_file -- the TargetFile-object where the received bytes
                       will be written to
        chunk -- the chunk which will be loaded first by this slot.
        connection -- the connection which should be used by this slot
                      for the first chunk. This can be the connection of
                      a InfoSlot.
        """
        self.chunk_started_event = EventListener()
        self.chunk_finished_event = EventListener()
        self.chunk_failed_event = EventListener()

        self._download = download
        self._log = download.log
        self._target_file = target_file
        self._chunk = chunk
        self.connection = connection
        self.data_received = False
        Thread.__init__(self, name=name)

    def run(self):
        """Called when the slot-thread is started.

        The slot will wait for a chunk-job on a Download's chunk_queue.
        Then it requests the Source to use from the Download.
        Maybe it will wait some seconds before start loading the data
        using a Connection-object.
        Using EventListeners the download will be informed about events.
        """
        while self._download.is_loading():
            self.data_received = False

            while self._chunk is None:
                try:
                    self._chunk = self._download.chunk_queue.get(True, 0.2)
                except Empty, e:
                    self._chunk = None

                # Download may be paused --> stop downloading
                if not self._download.is_loading():
                    return

            if self._chunk.length is None:
                self._log.add_log_entry(MessageType.info, self.getName(),
                        'Got new chunk-job (offset={0})!'.format(
                                    self._chunk.offset + self._chunk.loaded))
            else:
                self._log.add_log_entry(MessageType.info, self.getName(),
                        'Got new chunk-job (offset={0}, length={1})!'.format(
                                    self._chunk.offset + self._chunk.loaded,
                                    self._chunk.length - self._chunk.loaded))

            source, wait_until = None, 0
            if self.connection is None:
                # request source
                source, wait_until = self._download.get_next_source()

                self._download.source_condition.acquire()
                while source is None and self._download.is_loading():
                    self._log.add_log_entry(MessageType.info, self.getName(),
                                            'Waiting for a source!')
                    self._download.source_condition.wait()
                    if self._download.is_loading():
                        source, wait_until = self._download.get_next_source()

                self._download.source_condition.release()

            else:
                # use source of current connection (from InfoSlot)
                source, wait_until = (self.connection.source,
                                    self.connection.source.is_retry_allowed())

            # source may be None, e.g. when max retries is reached
            # on each source, or source does not support more slots
            if source is None:
                self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
                return

            self._log.add_log_entry(MessageType.info, self.getName(),
                                    'Using the source {0}'.format(source.url))

            # maybe we need to wait some seconds between retries
            to_wait = wait_until - time()
            if to_wait > 0:
                self._log.add_log_entry(MessageType.info, self.getName(),
                                    'Retry in {0} seconds!'.format(to_wait))
                # wait until retry, but still check if state has changed
                while time() < wait_until:
                    sleep(0.2)
                    if not self._download.is_loading():
                        return

            # Download may be paused --> stop downloading
            #if not self._download.is_loading():
            #    print(self.getName() + ': DL is not loading anymore (state changed)')
            #    return

            # is chunk still valid? (after waiting retry-time)
            self._download.fix_chunk(self._chunk)
            if self._chunk.length == 0:
                self.chunk_finished_event.signal(source, data_received=self.data_received)
                return

            # use already opened connection (from InfoSlot)
            c = self.connection
            if c is None:
                c = Connection(source)

            def received_listener():
                source.inc_active_slots()
                self.data_received = True
                self.chunk_started_event.signal(self._chunk)

            def on_fetch_stopped():
                if self.data_received:
                    source.inc_active_slots(decrement=True)

            c.data_received_event.add_listener(received_listener)
            try:
                c.fetch_data(self._chunk, self._target_file, self._download)
            except HTTPError, e:
                on_fetch_stopped()
                source.add_fail(self.data_received)
                self._log.add_log_entry(MessageType.error, self.getName(),
                                        'HTTP-Error: ' + str(e))
                self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
            except ChunkNotFinishedError, e:
                on_fetch_stopped()
                if e.critical:
                    source.add_fail(self.data_received)
                    self._log.add_log_entry(MessageType.error, self.getName(),
                                            str(e.reason))
                    self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
                else:
                    # Chunk not finished, because download was paused
                    # etc.
                    self._log.add_log_entry(MessageType.info, self.getName(),
                                            str(e.reason))
                    self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
            except URLError, e:
                on_fetch_stopped()
                source.add_fail(self.data_received)
                self._log.add_log_entry(MessageType.error, self.getName(),
                                        'Error: ' + str(e.reason))
                self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
            except TargetFileIOError, e:
                on_fetch_stopped()
                self._log.add_log_entry(MessageType.error, self.getName(),
                                        'IOError: ' + str(e))
                self.chunk_failed_event.signal(self._chunk, source, ioerror=True,
                                            data_received=self.data_received)
            except IOError, e:
                on_fetch_stopped()
                source.add_fail(self.data_received)
                self._log.add_log_entry(MessageType.error, self.getName(),
                                        'IOError: ' + str(e))
                self.chunk_failed_event.signal(self._chunk, source, ioerror=False,
                                            data_received=self.data_received)
            else:
                on_fetch_stopped()
                self.chunk_finished_event.signal(source,
                                            data_received=self.data_received)

            # Do not use connection/chunk multiple times!
            self.connection = None
            self._chunk = None
