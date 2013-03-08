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

"""The download-module contains classes for downloading files.

The DownloadState class is used to specify the state of a download.
The Download class represents a download with all its sources, slots,
chunks etc..
"""

from datetime import datetime
from os import path, rename, remove
from Queue import Queue
import thread
from threading import Lock, RLock, Condition

from chunk import Chunk
from event.eventlistener import EventListener
from log import Log, MessageType
from slot import InfoSlot, DataSlot
from source import Source
from targetfile import TargetFile


class DownloadState:
    """Used to specify the current state of a Download."""
    ready = 0
    fetching_info = 1
    loading = 2
    paused = 4
    cancelled = 8
    failed = 16
    finished = 32
    stopping = 64


class Download:
    """The download class is used to control the download.

    It contains methods to start/pause the download and change the state
    etc..

    Public instance variables:
    target_folder -- the folder where the file will be saved to
    filesize -- the size of the download. It may be None if unknown.
    slots_supported -- True, if slots are supported, otherwise False.
                       The default value is False. It will be set to
                       True automatically if a second slot receives
                       data.
    log -- the download-log where errors etc. will be logged
    chunks -- all chunks of the download (unfinished and finished)
    chunk_queue -- the current chunk-todo-list. A DataSlot will take
                   a chunk from this queue and load it.
    active_slot -- the number of currently loading slots
    max_slot -- the maximum number of slots to use
    chunk_size --
    source_condition --

    status_changed_event   -- An event.eventlistener.EventListener
                              object. The event is signalled when the
                              status has changed. The listener is called
                              with the download as argument.
    filename_changed_event -- An event.eventlistener.EventListener
                              object. The event is signalled when the
                              filename has changed. The listener is
                              called with the download as argument.
    filesize_changed_event -- An event.eventlistener.EventListener
                              object. The event is signalled when the
                              file size has changed. The listener is
                              called with the download as argument.
    slots_changed_event    -- An event.eventlistener.EventListener
                              object. The event is signalled when the
                              number of loading slots or the max. number
                              of slots has changed. The listener is
                              called with the download as argument.
    retries_changed_event  -- An event.eventlistener.EventListener
                              object. The event is signalled when the
                              number of retries or the max. number of
                              retries has changed. The listener is
                              called with the download as argument.
    source_added_event     --
    """


    def __init__(self, max_slot, source, target_folder):
        """Initialize the download.

        max_slot -- the maximum number of slots to use
        source -- the first Source to use
        target_folder -- the path of the folder where the file should be
                         saved to
        """
        self._state_lock = RLock()
        self._active_slot_lock = Lock()
        self._sources_lock = Lock()
        self._chunk_lock = RLock()

        self.source_condition = Condition()

        self.status_changed_event = EventListener()
        self.filename_changed_event = EventListener()
        self.filesize_changed_event = EventListener()
        self.slots_changed_event = EventListener()
        self.retries_changed_event = EventListener()
        self.source_added_event = EventListener()

        self.chunk_size = 2097152
        self.set_max_slot(max_slot)
        self.active_slot = 0
        self._slots = []
        self.filesize = None
        self._infos_fetched = False
        self.slots_supported = False
        self.log = Log()
        self._sources = []
        self.add_source(source)
        self._last_used_source = None
        self.target_folder = target_folder
        self._target_file = None
        self._set_filename(self._sources[0].filename, True)
        self.chunks = []
        self.chunk_queue = Queue()
        self._info_slot = None
        self._is_resuming = False

        self.state = None
        self.ready()

    @staticmethod
    def create_from_dict(dict):
        # TODO: validate values?!
        chunks = []
        if dict['root_chunk'] is not None:
            root_chunk = Chunk.create_from_dict(dict['root_chunk'])
            chunks.append(root_chunk)
            toadd = root_chunk.childs[:]
            while len(toadd) > 0:
                chunk = toadd.pop()
                for child in chunk.childs:
                    toadd.append(child)
                chunks.append(chunk)
        sources = []
        for source in dict['sources']:
            sources.append(Source.create_from_dict(source))

        dl = Download(dict['max_slot'], sources[0], dict['target_folder'])
        dl.chunk_size = dict['chunk_size']
        dl.filesize = dict['filesize']
        dl._infos_fetched = dict['infos_fetched']
        dl.slots_supported = dict['slots_supported']
        dl._last_used_source = dict['last_used_source']
        dl._original_filename = dict['original_filename']
        dl.filename = dict['filename']
        dl._set_state(dict['state'])
        dl._sources = sources
        dl.chunks = chunks
        return dl

    def get_as_dict(self):
        root_chunk = None
        with self._chunk_lock:
            if len(self.chunks) >= 1:
                root_chunk = self.chunks[0].get_as_dict()
        sources = []
        with self._sources_lock:
            for source in self._sources:
                sources.append(source.get_as_dict())
        download = {
            'chunk_size': self.chunk_size,
            'max_slot': self.max_slot,
            'filesize': self.filesize,
            'infos_fetched': self._infos_fetched,
            'slots_supported': self.slots_supported,
            'last_used_source': self._last_used_source,
            'target_folder': self.target_folder,
            'original_filename': self._original_filename,
            'filename': self.filename,
            'state': self.state,
            'sources': sources,
            'root_chunk': root_chunk
        }
        return download

    def get_bytes_loaded(self):
        """Returns the number of loaded bytes."""
        loaded = 0
        with self._chunk_lock:
            for chunk in self.chunks:
                loaded += chunk.bytes_loaded(self.slots_supported)
        return loaded

    def get_retries(self):
        retries = 0
        max_retries = 0
        with self._sources_lock:
            for source in self._sources:
                retries += source.retries
                if source.max_retries < 0:
                    max_retries = -1
                if max_retries >= 0:
                    max_retries += source.max_retries
        return (retries, max_retries)

    def get_next_source(self):
        """Get the next Source that will be used by a DataSlot.

        Usually this method is called by a DataSlot.
        It searches for a Source that can be used to load data from.
        So the returned Source does not have reached max_retries.

        If a Source was found a tuple is returned containing the Source
        and the time until the slot should wait (if an error happend
        before using the Source).

        If no Source was found the download is failed! A (None, None)-
        tuple will be returned.
        """
        self._sources_lock.acquire()

        if self._last_used_source is None:
            self._last_used_source = 0
        else:
            self._last_used_source += 1
            self._last_used_source %= len(self._sources)

        # check sources in order, beginning at self._last_used_source
        error = True
        all_source_invalid = True

        source = None
        wait_until = None
        start = self._last_used_source
        length = len(self._sources)
        for i in [i%length for i in range(start, length+start)]:
            cur_source = self._sources[i]
            if not cur_source.valid:
                continue
            if self.filesize != cur_source.filesize:
                cur_source.valid = False
                server = cur_source.url
                self.log.add_log_entry(MessageType.warning, 'Download',
                    'Skipped source (invalid file size): {0}'.format(server))
                continue
            all_source_invalid = False
            # reached max. parallel slots of this source?
            if (cur_source.max_slots_determined and
                    cur_source.running_slots >= cur_source.max_active_slots):
                error = False
                continue
            # check if source reached max. retries
            tmp = cur_source.is_retry_allowed()
            if tmp >= 0:
                error = False
                source = cur_source
                wait_until = tmp
                break
            else:
                cur_source.valid = False

        download_failed = all_source_invalid or error
        if download_failed:
            # reached max. retries on each source
            self.log.add_log_entry(MessageType.warning, 'Download',
                                    'No valid source found. Maybe reached ' +
                                    'max. number of retries of all sources!')
            self.failed()

        if source is not None:
            source.inc_running_slots()

        self._sources_lock.release()
        return (source, wait_until)

    def get_chunk_data(self):
        chunks = []
        with self._chunk_lock:
            for chunk in self.chunks:
                chunks.append((chunk.offset,
                                chunk.bytes_loaded(self.slots_supported)))
        return chunks

    def is_loading(self):
        """Returns True if the Download is loading, otherwise False."""
        return self.state == DownloadState.loading

    def is_fetching_info(self):
        """Returns True if the Download is fetching information,
        otherwise False.
        """
        return self.state == DownloadState.fetching_info

    def set_max_slot(self, num):
        """Set the maximum number of slots."""
        self.max_slot = int(num)
        self.slots_changed_event.signal(self)

    def fix_chunk(self, chunk):
        """This method is used to fix a chunk if it overlaps with its
        parent chunk. It is called by a DataSlot.

        The root chunk and its childs may overlap.
        This can only happen if the first slot is loading and all other
        slots permanently fail. So these slots may wait some seconds
        before retrying.
        While these slots are waiting, the root chunk may load more
        than "length" bytes, because self.slots_supported == False.
        Now if one of these failing slots eventually can load data, we
        need to fix the offset and length of the chunk because some
        bytes may already be loaded by the root chunk and we want to avoid
        loading bytes multiple times.

        Note: The root chunk may be modified, too.

        chunk -- the chunk to check/fix
        """
        with self._chunk_lock:
            root = self.chunks[0]
            if chunk.parent != root:
                # chunk is not child of root chunk
                return

            # implicite: root.offset == 0
            if root.loaded > chunk.offset:
                # root chunk has loaded some bytes of the child chunk

                # how many bytes of the child, has the root already loaded?
                overlap = root.loaded - chunk.offset
                if overlap > chunk.length:
                    overlap = chunk.length

                # Fix length of the root. (may be increased (max. by the
                # number of already loaded bytes))
                if chunk.offset + overlap > root.length:
                    root.length = chunk.offset + overlap

                # Fix offset/length of chunk. Maybe no more bytes need
                # to be loaded of the chunk.
                chunk_new_offset = chunk.offset + overlap
                chunk_new_length = chunk.length - overlap

                if (chunk_new_length <= 0 or
                    chunk_new_offset >= chunk.offset+chunk.length):
                    # the chunk was completely loaded via root chunk
                    # chunk.offset = None
                    chunk.length = 0
                    chunk.original_length = 0
                    print('FIXED CHUNK: chunk deleted, root loaded ' + str(root.loaded))

                else:
                    chunk.offset = chunk_new_offset
                    chunk.length = chunk_new_length
                    print('FIXED CHUNK: chunk edited, ro='+str(root.offset)+', rlo='+str(root.loaded)+', rle='+str(root.length)+', co='+str(chunk.offset)+', clo='+str(chunk.loaded)+', cle='+str(chunk.length))

    def ready(self):
        """Set the state of the download to DownloadState.ready."""
        self._set_state(DownloadState.ready)

    def pause(self):
        """Set the state of the download to DownloadState.paused."""
        self._set_state(DownloadState.paused)

    def cancel(self):
        """Set the state of the download to DownloadState.cancelled."""
        self._set_state(DownloadState.cancelled)

    def failed(self):
        """Set the state of the download to DownloadState.failed."""
        self._set_state(DownloadState.failed)

    def start(self):
        """Start or resume the download.

        If the information have not been fetched yet, they will be
        fetched. The download will then automatically resume.
        Otherwise the download will be resumed.
        """
        if self._infos_fetched:
            self.log.add_log_entry(MessageType.info, 'Download', 'Resuming')
            self._is_resuming = True
            self._resume()
        else:
            self.log.add_log_entry(MessageType.info, 'Download', 'Starting')
            self.log.add_log_entry(MessageType.info, 'Download',
                                                        'Fetching Information')
            # fetch download-infos (filename, filesize, ...)
            self._set_state(DownloadState.fetching_info)
            self._info_slot = InfoSlot('Info Slot', self._sources[0], self,
                                 self._on_infos_fetched, self._on_infos_failed)
            self._info_slot.start()
            # --> _on_infos_fetched or _on_infos_failed will be called
            #       (nothing will be called if download will pause etc.)

    def add_source(self, source):
        with self._sources_lock:
            self._sources.append(source)
            source.retries_changed_event.add_listener(
                                            self._on_source_retries_changed)
        self.source_added_event.signal(self, source)
        self.retries_changed_event.signal(self)
        # Maybe there are slots waiting for a source.
        with self.source_condition:
            self.source_condition.notifyAll()

    def remove_source(self, source):
        removed = True
        with self._sources_lock:
            if self._sources.index(source) == 0:
                # You cannot remove root source!
                removed = False
            else:
                try:
                    self._sources.remove(source)
                except ValueError, e:
                    removed = False
                else:
                    source.retries_changed_event.remove_listener(
                                            self._on_source_retries_changed)

        if removed:
            self.retries_changed_event.signal(self)
        return removed

    def get_copy_of_sources(self):
        with self._sources_lock:
            copy = self._sources[:]
        return copy

    def _fix_filename(self, ignore_temp=False):
        """Fix the filename.

        For example if a file with the name already exist, a number is
        appended to the filename.

        ignore_temp -- If True, it is ignored if the file with the temp-
                       extension (.dl) already exist. This is useful if
                       the download is finished and the temp-file should
                       be renamed.
        """
        name, ext, ext_count = self._original_filename, '', self._ext_count
        if ext_count > 0:
            ext = '(' + str(ext_count) + ')'
        new_file = path.join(self.target_folder, name)
        while (path.exists(new_file + ext) or
               (not ignore_temp and path.exists(new_file + ext + '.dl'))):
            ext_count += 1
            ext = '(' + str(ext_count) + ')'
        self._set_filename(name, ext_count=ext_count)

    def _set_filename(self, filename, change_original_name=False, ext_count=0):
        """Change the filename of the download.

        filename_changed_event will be signalled.

        filename -- the new filename
        change_original_name -- a boolean specifying if the original
                                filename should be changed, too
        ext_count -- specifies the number that will be appended to the
                     filename (if ext_count > 0)
        """
        self._ext_count = ext_count
        if ext_count > 0:
            filename += '(' + str(ext_count) + ')'
        if change_original_name:
            self._original_filename = filename
        self.filename = filename
        self.filename_changed_event.signal(self)

    def _set_filesize(self, filesize):
        self.filesize = filesize
        self.filesize_changed_event.signal(self)

    def _is_valid_state_change(self, new_state):
        if self.state == DownloadState.stopping:
            return False

        ready = (new_state == DownloadState.ready and
                            (self.state is None or
                             self.state == DownloadState.paused or
                             self.state == DownloadState.cancelled))
        info = (new_state == DownloadState.fetching_info and
                            self.state == ready)
        loading = (new_state == DownloadState.loading and
                            (self.state == DownloadState.ready or
                             self.state == DownloadState.fetching_info))
        paused = (new_state == DownloadState.paused and
                            (self.state == DownloadState.ready or
                             self.state == DownloadState.fetching_info or
                             self.state == DownloadState.loading))
        cancelled = (new_state == DownloadState.cancelled and
                            (self.state == DownloadState.ready or
                             self.state == DownloadState.fetching_info or
                             self.state == DownloadState.loading or
                             self.state == DownloadState.paused))
        failed = (new_state == DownloadState.failed and
                            (self.state == DownloadState.ready or
                             self.state == DownloadState.fetching_info or
                             self.state == DownloadState.loading))
        finish = (new_state == DownloadState.finished and
                            (self.state == DownloadState.ready or
                             self.state == DownloadState.fetching_info or
                             self.state == DownloadState.loading))

        if ready or info or loading or paused or cancelled or failed or finish:
            return True

        return False

    def _set_state(self, state):
        """Change the state of the download.

        If the new state is one of paused, cancelled, failed or finished
        the method will wait for all Slots to finish.

        state -- the new DownloadState
        """
        # state lock:
        # User should not be able to pause and start again quickly!
        # We need to wait for the slots to exit!
        if not self._state_lock.acquire(False):
            return False

        if not self._is_valid_state_change(state):
            self._state_lock.release()
            return False

        """
        """
        if (state == DownloadState.paused or
            state == DownloadState.cancelled or
            state == DownloadState.failed or
            state == DownloadState.finished):

            def clean_up(self, state):
                # maybe we need to wait for InfoSlot
                if self._info_slot is not None:
                    self._info_slot.join()

                # dl should stop, so wait for slots
                for slot in self._slots:
                    slot.join()

                if self._target_file is not None:
                    self._target_file.close()

                # clear chunk-todo-list
                while not self.chunk_queue.empty():
                    self.chunk_queue.get_nowait()

                if state == DownloadState.cancelled:
                    # reset loaded data
                    with self._chunk_lock:
                        del self.chunks[:]
                    if (self._target_file is not None and
                            path.exists(self._target_file.target_file)):
                        remove(self._target_file.target_file)

                self.state = state
                if state == DownloadState.paused:
                    self.log.add_log_entry(MessageType.info, 'Download',
                                            'Paused')
                elif state == DownloadState.cancelled:
                    self.log.add_log_entry(MessageType.info, 'Download',
                                            'Cancelled')
                elif state == DownloadState.failed:
                    self.log.add_log_entry(MessageType.error, 'Download',
                                            'Failed')
                self.status_changed_event.signal(self)

            self.state = DownloadState.stopping
            self.log.add_log_entry(MessageType.info, 'Download', 'Stopping')
            # maybe there are slots waiting for a source which are
            # interested in state-changes
            with self.source_condition:
                self.source_condition.notifyAll()
            self.status_changed_event.signal(self)
            self._state_lock.release()

            thread.start_new_thread(clean_up, (self, state, ))

        else:
            self.state = state
            if state == DownloadState.ready:
                self.log.add_log_entry(MessageType.info, 'Download', 'Ready')
            # maybe there are slots waiting for a source which are
            # interested in state-changes
            with self.source_condition:
                self.source_condition.notifyAll()
            self.status_changed_event.signal(self)
            self._state_lock.release()

        return True

    def _inc_active_slots(self, decrement=False):
        with self._active_slot_lock:
            if decrement:
                self.active_slot -= 1
            else:
                self.active_slot += 1
        self.slots_changed_event.signal(self)

    def _unfinished_chunks_count(self):
        """Calculate and return the number of unfinished chunks.

        Note: A chunk which has an unknown length will always be
              treated as an unfinished chunk.
        """
        count = 0
        with self._chunk_lock:
            for chunk in self.chunks:
                if not chunk.is_finished(self.slots_supported):
                    count += 1
        return count

    def _resume(self):
        """Resume downloading the file.

        The target file will be opened first. Then the chunks will be
        added to the chunk_queue and the slots will be started.
        """
        self._set_state(DownloadState.loading)

        file = path.join(self.target_folder, self.filename + '.dl')
        if self._is_resuming and not path.exists(file):
            self.log.add_log_entry(MessageType.error, 'Download',
                        'The file "{0}" does not exist anymore.'.format(file))
            self.failed()
            return

        self._target_file = TargetFile(file)
        try:
            self._target_file.open()
        except IOError, e:
            self.log.add_log_entry(MessageType.error, 'Download',
                                    'IOError: ' + str(e))
            self.failed()
            return

        # When resuming, slots MUST be supported!
        if self._is_resuming:
            self.slots_supported = True

        # If self._is_resuming == True we can just enqueue all unfinished
        # chunks.
        # If self._is_resuming == False we only just fetched the infos
        # and can use the connection of the InfoSlot for the first
        # DataSlot to load the root chunk.

        with self._chunk_lock:
            if len(self.chunks) == 0:
                # this is the first time, the download is started
                root_chunk = Chunk(None, 0, self.filesize)
                self.chunks.append(root_chunk)

            # Enqueue unfinished chunks
            to_enqueue = None
            if self._is_resuming:
                to_enqueue = self.chunks
            else:
                # Do not enqueue root chunk. It will be passed to the
                # first DataSlot manually. (s.b.)
                to_enqueue = self.chunks[1:]

            filled_queue = False
            for chunk in to_enqueue:
                if not chunk.is_finished(self.slots_supported):
                    filled_queue = True
                    self.chunk_queue.put(chunk)

        # Maybe all chunks were already loaded. This can happen when
        # download was paused and one slot still finished the last
        # chunk.
        if not filled_queue and self._is_resuming:
            self._finish()
            return

        # Start slots. They are waiting for chunk-"jobs".
        slots_to_create = 0
        if self.filesize is None:
            slots_to_create = 1
        else:
            slots_to_create = self.max_slot

        for i in range(slots_to_create):
            slot = None
            if self._is_resuming or i > 0:
                slot = DataSlot('Slot ' + str(i), self, self._target_file)
            else:
                # Use the connection of the InfoSlot to load the root
                # chunk in the first slot.
                slot = DataSlot('Slot ' + str(i), self, self._target_file,
                                self.chunks[0], self._info_slot.connection)
                self._sources[0].inc_running_slots()
            self._slots.append(slot)
            slot.chunk_started_event.add_listener(self._on_slot_started_chunk)
            slot.chunk_finished_event.add_listener(
                                                self._on_slot_finished_chunk)
            slot.chunk_failed_event.add_listener(self._on_slot_failed_chunk)
            slot.start()

    def _get_max_supported_slots(self):
        max_slots = 0
        with self._sources_lock:
            for source in self._sources:
                if source.valid:
                    if source.max_slots_determined:
                        max_slots += source.max_active_slots
                    else:
                        max_slots = -1
                        break
        return max_slots

    def _new_chunk(self):
        """This method is used to split up existing chunks into two
        chunks.

        So the slot with the old chunk (parent) will load less data and
        the new chunk (child) will be loaded by another slot.
        """
        if not self.is_loading():
            return

        with self._chunk_lock:
            # the max. number of slots supported by the sources
            max_slots = self._get_max_supported_slots()
            unfinished_chunks = self._unfinished_chunks_count()
            # split existing chunk only if there are still waiting slots
            if (unfinished_chunks >= self.max_slot or
                    (max_slots >= 0 and unfinished_chunks >= max_slots)):
                return

            chunk_to_split = None
            chunk_to_load = 0
            for chunk in self.chunks:
                if not chunk.is_finished(self.slots_supported):
                    bytes = chunk.bytes_left(self.slots_supported)
                    # respect minimum chunk size, e.g. 2 MB
                    if bytes >= self.chunk_size and bytes > chunk_to_load:
                        chunk_to_split = chunk
                        chunk_to_load = bytes

            if chunk_to_split is not None:
                old_length = chunk_to_split.length
                chunk_to_split.length = old_length - (chunk_to_load / 2)
                new_chunk_offset = (chunk_to_split.offset +
                                    chunk_to_split.length)
                new_chunk_length = old_length - chunk_to_split.length
                new_chunk = Chunk(chunk_to_split,
                                  new_chunk_offset, new_chunk_length)
                chunk_to_split.childs.append(new_chunk)
                self.chunks.append(new_chunk)
                self.chunk_queue.put(new_chunk)

    def _on_infos_fetched(self):
        """This method will be called if infos were fetched successfully
        from a Source.

        The download's data like filename and size will be changed to
        match those of the Source.
        """
        s = self._sources[0]
        self._set_filename(s.filename, True)
        self._set_filesize(s.filesize)
        self._infos_fetched = True
        self._fix_filename()
        self.log.add_log_entry(MessageType.info, 'Download', 'New filename: ' +
                                                                self.filename)
        if self.filesize is not None:
            self.log.add_log_entry(MessageType.info, 'Download',
                                'New file size: ' + str(self.filesize) + ' B')
        else:
            self.log.add_log_entry(MessageType.warning, 'Download',
                                                        'Unknown file size!')
        self._resume()

    def _on_infos_failed(self):
        """This method is called if fetching information has failed."""
        self.log.add_log_entry(MessageType.warning, 'Download',
                'Failed to fetch information! Reached max. number of retries!')
        self.failed()

    def _on_slot_started_chunk(self, chunk):
        """This method is called if a chunk has started receiving data.

        This means that a new slot is active and we may create more
        chunks.
        """
        self._inc_active_slots()

        if chunk != self.chunks[0]:
            self.slots_supported = True

        # we can only use multiple slots if we know the filesize
        if self.filesize is not None:
            self._new_chunk()

    def _finish(self):
            if not self._set_state(DownloadState.finished):
                return  # maybe already set finished in another thread
            self.log.add_log_entry(MessageType.info, 'Download', 'Finish')

            self._fix_filename(ignore_temp=True)
            new_file = path.join(self.target_folder, self.filename)

            if path.exists(self._target_file.target_file):
                try:
                    rename(self._target_file.target_file, new_file)
                except OSError, e:
                    self.log.add_log_entry(MessageType.warning, 'Download',
                        ('Could not rename the temp-file to "{0}"! Maybe' +
                        'the target file already exist!').format(new_file))
            else:
                self.log.add_log_entry(MessageType.warning, 'Download',
                    ('The file "{0}" does not exist anymore! ' +
                        'Renaming failed!').format(
                                                self._target_file.target_file))


    def _on_slot_finished_chunk(self, source, data_received):
        """This method is called if a chunk was finished by a slot.

        If there is no other unfinished chunk, the download is finished.
        Otherwise a new chunk will be created. So the slot which
        finished the chunk will not idle.

        data_received -- True, if bytes of the chunk were loaded,
                         otherwise False.
        """
        source.inc_running_slots(decrement=True)

        if data_received:
            self._inc_active_slots(decrement=True)

        # Maybe there are slots waiting for a source.
        # Since a chunk is finished, a source is available now.
        with self.source_condition:
            self.source_condition.notifyAll()

        # loaded all chunks? (== download finished?)
        # If filesize is unknown, only 1 slot exist. So if this method
        # is called and self.filesize == None, the download is finished.
        if self._unfinished_chunks_count() == 0 or self.filesize is None:
            self._finish()

        else:
            self._new_chunk()

    def _on_slot_failed_chunk(self, chunk, source, ioerror, data_received):
        """This method is called if loading a chunk has failed.

        If the error was an file-ioerror, e.g. permission denied, the
        download has failed! If not, the failed chunk will be put back
        to the chunk_queue.
        """
        if source is not None:
            source.inc_running_slots(decrement=True)

        if data_received:
            self._inc_active_slots(decrement=True)

        if ioerror:
            # e.g. disk full, no permissions
            self.failed()

        # Maybe there are slots waiting for a source.
        # Since a chunk is failed, a source is available now.
        with self.source_condition:
            self.source_condition.notifyAll()

        # chunk still needs to be loaded
        self.chunk_queue.put(chunk)

    def _on_source_retries_changed(self, source):
        self.retries_changed_event.signal(self)
