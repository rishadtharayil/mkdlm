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
import ctypes
from os.path import realpath, dirname, join
from threading import Lock, RLock
from urlparse import urlparse

import pygtk
pygtk.require("2.0")
import gtk
import gobject

from dlm.download import Download, DownloadState
from dlm.source import Source
from dlm.log import MessageType
from globals import settings, downloads_file
from gui.chunkprogress import ChunkProgress
from gui.meter import ToolMeter
from gui.new_download_window import NewDownloadWindow
from gui.new_source_window import NewSourceWindow
from gui.settings_dialog import SettingsDialog


class MainWindow:
    def __init__(self, manager):
        builder = gtk.Builder()
        glade = join(dirname(realpath(__file__)), 'main_window.glade')
        builder.add_from_file(glade)

        self.window = builder.get_object("main_window")
        self.aboutdialog = builder.get_object("aboutdialog")

        # 0:download 1:filename 2:loaded 3:size 4:progress
        # 5:state 6:retries 7:max_retries 8:slots 9:max_slots 10:speed
        self.download_store = gtk.ListStore(object, str, long, object, int,
                                            int, int, int, int, int, int)
        self.download_view = builder.get_object("download_view")
        self.download_view.set_model(model=self.download_store)

        # using Glade the progressbar will not be expanded in its cell
        # so we define our own CellRendererProgress
        progress_cell = gtk.CellRendererProgress()
        self.progress_column = builder.get_object("progress_column")
        self.progress_column.pack_start(progress_cell, True)
        self.progress_column.set_cell_data_func(progress_cell,
                                            self._get_download_progress)

        stateicon_cell = builder.get_object("state_cellrendererpixbuf")
        self.filename_column = builder.get_object("filename_column")
        self.filename_column.set_cell_data_func(stateicon_cell,
                                                self._get_download_state_icon)

        state_cell = builder.get_object("state_cellrenderertext")
        self.state_column = builder.get_object("state_column")
        self.state_column.set_cell_data_func(state_cell, self._get_download_state)

        slots_cell = builder.get_object("slots_cellrenderertext")
        self.slots_column = builder.get_object("slots_column")
        self.slots_column.set_cell_data_func(slots_cell, self._get_download_slots)

        retries_cell = builder.get_object("retries_cellrenderertext")
        self.retries_column = builder.get_object("retries_column")
        self.retries_column.set_cell_data_func(retries_cell,
                                            self._get_download_retries)

        speed_cell = builder.get_object("speed_cellrenderertext")
        self.speed_column = builder.get_object("speed_column")
        self.speed_column.set_cell_data_func(speed_cell, self._get_download_speed)

        timeleft_cell = builder.get_object("timeleft_cellrenderertext")
        self.timeleft_column = builder.get_object("timeleft_column")
        self.timeleft_column.set_cell_data_func(timeleft_cell,
                                                self._get_download_time_left)

        # toolbar
        toolbar = builder.get_object("toolbar")
        toolmeter = ToolMeter()
        self.speed_meter = toolmeter.meter
        speed_format = u'max: {0}/s,  \u2205 per min: {1}/s,  current: {2}/s'
        speed_text = (lambda speed, max_speed, avg_speed:
                        speed_format.format(self._format_bytes(max_speed),
                                            self._format_bytes(avg_speed),
                                            self._format_bytes(speed)))
        self.speed_meter.text_callback = speed_text
        toolbar.insert(toolmeter, 7)
        toolmeter.show_all()

        # chunk progress
        general_table = builder.get_object("general_table")
        self.chunk_progress = ChunkProgress()
        general_table.attach(self.chunk_progress, 0, 1, 0, 1,
            xoptions=gtk.EXPAND|gtk.FILL, yoptions=gtk.FILL)
        self.chunk_progress.show_all()

        # icon, datetime, name, message
        self.log_store = gtk.ListStore(str, object, str, str)
        self.log_scrolled = builder.get_object('log_scrolled')
        self.log_view = builder.get_object("log_view")
        self.log_view.set_model(model=self.log_store)

        message_cell = builder.get_object("message_cellrenderertext")
        entry_column = builder.get_object("entry_column")
        entry_column.set_cell_data_func(message_cell, self._get_message_text)

        # source, name
        self.sources_store = gtk.ListStore(object, str)
        self.sources_view = builder.get_object("sources_view")
        self.sources_view.set_model(model=self.sources_store)

        source_cell = builder.get_object("source_cellrenderertext")
        source_column = builder.get_object("source_column")
        source_column.set_cell_data_func(source_cell, self._get_source_text)

        # info-labels
        self.filename_label = builder.get_object("filename_label")
        self.filesize_label = builder.get_object("filesize_label")
        self.folder_label = builder.get_object("folder_label")
        self.slots_label = builder.get_object("slots_label")
        self.maxslot_label = builder.get_object("maxslot_label")

        self.source_url_label = builder.get_object("source_url_label")
        self.source_realurl_label = builder.get_object("source_realurl_label")
        self.source_retries_label = builder.get_object("source_retries_label")
        self.source_wait_label = builder.get_object("source_wait_label")
        self.source_useragent_label = builder.get_object(
                                                    "source_useragent_label")
        self.source_referrer_label = builder.get_object(
                                                    "source_referrer_label")
        self.source_cookie_label = builder.get_object("source_cookie_label")

        self.parallel_spin = builder.get_object('parallel_spin')
        def parallel_spin_output(spin):
            digits = int(spin.props.digits)
            value = spin.props.value
            if value == 0:
                spin.props.text = u"\u221E"
            else:
                spin.props.text = '{0:.{1}f}'.format(value, digits)
            return True
        self.parallel_spin.connect('output', parallel_spin_output)

        def parallel_spin_input(spin, new_value):
            text = spin.get_text()
            if text == u"\u221E":
                value = 0
            else:
                try:
                    value = float(text)
                except ValueError:
                    return -1
            p = ctypes.c_double.from_address(hash(new_value))
            p.value = value
            return True
        self.parallel_spin.connect('input', parallel_spin_input)

        # actions
        self.remove_download_action = builder.get_object(
                                                    "remove_download_action")

        # Locks
        self._download_list_lock = RLock()
        self._current_download_lock = RLock()
        self._log_lock = Lock()
        self._sources_lock = RLock()
        self._current_source_lock = RLock()

        self.current_download = None
        self.current_source = None

        self.manager = manager
        manager.download_added_event.add_listener(self._on_download_added)
        manager.max_parallel_downloads_changed_event.add_listener(
                                    self._on_max_parallel_downloads_changed)

        # DownloadMeter for speed and progress
        manager.download_meter.download_bytes_changed_event.add_listener(
                                            self._on_download_bytes_changed)
        manager.download_meter.download_speed_changed_event.add_listener(
                                            self._on_download_speed_changed)
        manager.download_meter.speed_changed_event.add_listener(
                                            self._on_speed_changed)

        # default values
        self.parallel_spin.set_value(self.manager.max_parallel_downloads)

        builder.connect_signals(self)

        # restore window settings
        x = settings.get_int('gui.main_window.x')
        y = settings.get_int('gui.main_window.y')
        if x is not None and y is not None:
            self.window.move(x, y)

        w = settings.get_int('gui.main_window.width')
        h = settings.get_int('gui.main_window.height')
        if w is not None and h is not None:
            self.window.resize(w, h)

        pw = settings.get_int('gui.main_window.progress_width')
        if pw is not None:
            self.progress_column.set_fixed_width(pw)
        fw = settings.get_int('gui.main_window.filename_width')
        if fw is not None:
            self.filename_column.set_fixed_width(fw)
        stw = settings.get_int('gui.main_window.state_width')
        if stw is not None:
            self.state_column.set_fixed_width(stw)
        slw = settings.get_int('gui.main_window.slots_width')
        if slw is not None:
            self.slots_column.set_fixed_width(slw)
        rw = settings.get_int('gui.main_window.retries_width')
        if rw is not None:
            self.retries_column.set_fixed_width(rw)
        spw = settings.get_int('gui.main_window.speed_width')
        if spw is not None:
            self.speed_column.set_fixed_width(spw)
        tw = settings.get_int('gui.main_window.timeleft_width')
        if tw is not None:
            self.timeleft_column.set_fixed_width(tw)

        parallel_dls = settings.get_int('core.manager.parallel_downloads', 1)
        self.manager.set_max_parallel_downloads(parallel_dls)

        self._update_colors()


    def start(self):
        gobject.threads_init()
        self.window.show()

        # load/add saved downloads
        downloads = self.manager.create_downloads_from_list(
                                        downloads_file.get('downloads', []))
        for d in downloads:
            for s in d.get_copy_of_sources():
                s.url_changed_event.add_listener(self._update_cur_source_labels)
                s.retries_changed_event.add_listener(self._update_cur_source_labels)

            d.log.message_added_event.add_listener(
                                                self._on_downloadlog_message_added)
            d.status_changed_event.add_listener(self._on_download_state_changed)
            d.filename_changed_event.add_listener(
                                                self._on_download_filename_changed)
            d.filesize_changed_event.add_listener(
                                                self._on_download_filesize_changed)
            d.slots_changed_event.add_listener(self._on_download_slots_changed)
            d.retries_changed_event.add_listener(self._on_download_retries_changed)
            d.source_added_event.add_listener(self._on_download_source_added)

            self.manager.add_download(d)

        gtk.main()

    def _quit(self):
        if self.manager._active_downloads > 0:
            dlg = gtk.MessageDialog(parent=self.window,
                                type=gtk.MESSAGE_WARNING,
                                buttons=gtk.BUTTONS_YES_NO,
                                message_format='You have running downloads! ' +
                                            'Are you shure you want to quit?')
            result = dlg.run()
            dlg.destroy()
            if result == gtk.RESPONSE_YES:
                return False  # window will be destroyed --> program quits
            return True  # do not quit
        else:
            return False  # quit

    def _get_download_progress(self, column, cell, model, iter):
        loaded = model.get_value(iter, 2)
        size = model.get_value(iter, 3)
        progress = model.get_value(iter, 4)

        loaded_str = self._format_bytes(loaded)

        if size is not None:
            size_str = self._format_bytes(size)
            cell.set_property('value', progress)
            cell.set_property('text',
                                str(progress) + '% - ' +
                                loaded_str + ' / ' +
                                size_str)
        else:
            cell.set_property('value', 0)
            cell.set_property('text', loaded_str)

    def _get_download_state(self, column, cell, model, iter):
        state_val = model.get_value(iter, 5)
        states = {DownloadState.ready: 'Ready',
                    DownloadState.fetching_info: 'Fetching Info',
                    DownloadState.loading: 'Loading',
                    DownloadState.paused: 'Paused',
                    DownloadState.cancelled: 'Cancelled',
                    DownloadState.failed: 'Failed',
                    DownloadState.finished: 'Finish',
                    DownloadState.stopping: 'Stopping'}

        cell.set_property('text', states[state_val])

    def _get_download_state_icon(self, column, cell, model, iter):
        state_val = model.get_value(iter, 5)
        states = {DownloadState.ready: 'mkdlm-dl-ready',
                    DownloadState.fetching_info: 'mkdlm-dl-loading',
                    DownloadState.loading: 'mkdlm-dl-loading',
                    DownloadState.paused: 'mkdlm-dl-paused',
                    DownloadState.cancelled: 'mkdlm-dl-cancelled',
                    DownloadState.failed: 'mkdlm-dl-failed',
                    DownloadState.finished: 'mkdlm-dl-finished',
                    DownloadState.stopping: 'mkdlm-dl-stopping'}

        cell.set_property('stock-id', states[state_val])

    def _get_download_slots(self, column, cell, model, iter):
        cell.set_property('text',
                            str(model.get_value(iter, 8)) + "/" +
                            str(model.get_value(iter, 9)))

    def _get_download_retries(self, column, cell, model, iter):
        retries_str = str(model.get_value(iter, 6))
        max_retries = model.get_value(iter, 7)
        if max_retries < 0:
            max_retries_str = u"\u221E"
        else:
            max_retries_str = str(max_retries)
        cell.set_property('text',
                            retries_str + "/" + max_retries_str)

    def _get_download_speed(self, column, cell, model, iter):
        state, speed = model.get_value(iter, 5), model.get_value(iter, 10)
        speed_str = self._format_bytes(speed)
        if state != DownloadState.loading and speed == 0:
            cell.set_property('text', '')
        else:
            cell.set_property('text', speed_str + '/s')

    def _get_download_time_left(self, column, cell, model, iter):
        state, speed = model.get_value(iter, 5), model.get_value(iter, 10)
        if state != DownloadState.loading or speed == 0:
            cell.set_property('text', '')
            return

        loaded, size = model.get_value(iter, 2), model.get_value(iter, 3)
        if size is None:
            cell.set_property('text', 'Unknown')
        else:
            bytes_left = size - loaded
            time_left = bytes_left / speed

            hours = time_left / 3600
            if hours > 0:
                time_left = time_left % (hours * 3600)

            minutes = time_left / 60
            if minutes > 0:
                time_left = time_left % (minutes * 60)

            time_str = '{0:02d}:{1:02d}:{2:02d}'.format(hours, minutes,
                                                                    time_left)
            cell.set_property('text', time_str)

    def _get_message_text(self, column, cell, model, iter):
        name, message = model.get_value(iter, 2), model.get_value(iter, 3)
        time =  model.get_value(iter, 1)
        time_str = '[{0:02d}:{1:02d}:{2:02d}] '.format(time.hour, time.minute,
                                                        time.second)
        cell.set_property('text', time_str + name + ': ' + message)

    def _get_source_text(self, column, cell, model, iter):
        server = model.get_value(iter, 1)
        cell.set_property('text', server)

    def _get_download_row(self, download):
        for row in self.download_store:
            if row[0] is download:
                return row
        return None

    def _download_progress(self, download, bytes=None):
        if download.filesize is None:
            return 0
        if download.filesize == 0:
            return 100
        if bytes is None:
            bytes = download.get_bytes_loaded()
        return float(bytes) / download.filesize * 100

    def _format_bytes(self, bytes):
        tmp = float(bytes)
        unit = 'B'
        if tmp > 1000:
            tmp /= 1024
            unit = 'KB'
        if tmp > 1000:
            tmp /= 1024
            unit = 'MB'
        if tmp > 1000:
            tmp /= 1024
            unit = 'GB'
        return ('{0:.2f} ' + unit).format(tmp)

    def _add_log_message(self, message):
        type, time, name, text = message
        icon = {MessageType.info: 'gtk-dialog-info',
                MessageType.error: 'gtk-dialog-error',
                MessageType.warning: 'gtk-dialog-warning'}
        self.log_store.append([icon[type], time, name, text])

    def _add_source(self, source):
        server = urlparse(source.original_url).netloc.strip()
        self.sources_store.append([source, server])

    def _on_download_added(self, download):
        def download_added():
            with self._download_list_lock:
                retries, max_retries = download.get_retries()
                d = [download,
                        download.filename,
                        download.get_bytes_loaded(),
                        download.filesize,
                        self._download_progress(download),
                        download.state,
                        retries,
                        max_retries,
                        download.active_slot,
                        download.max_slot,
                        0]
            self.download_store.append(d)

        gobject.idle_add(download_added)

    def _on_max_parallel_downloads_changed(self):
        self.parallel_spin.set_value(self.manager.max_parallel_downloads)

    def _update_cur_download_filename(self, download):
        def update_cur_download():
            with self._current_download_lock:
                if download is self.current_download:
                    if download is None:
                        self.filename_label.set_text('')
                    else:
                        self.filename_label.set_text(download.filename)
        gobject.idle_add(update_cur_download)

    def _update_cur_download_filesize(self, download):
        def update_cur_download():
            with self._current_download_lock:
                if download is self.current_download:
                    if download is None:
                        self.filesize_label.set_text('')
                    else:
                        if self.current_download.filesize is None:
                            self.filesize_label.set_text('Unknown')
                        else:
                            size_format = self._format_bytes(download.filesize)
                            size_str = str(download.filesize)
                            self.filesize_label.set_text(
                                    '{0} ({1} B)'.format(size_format,size_str))
        gobject.idle_add(update_cur_download)

    def _update_cur_download_progress(self, download):
        def update_cur_download():
            with self._current_download_lock:
                if download is self.current_download:
                    if download is None:
                        self.chunk_progress.set_chunks([], None)
                    else:
                        chunks = download.get_chunk_data()
                        self.chunk_progress.set_chunks(chunks,
                                                        download.filesize)
        gobject.idle_add(update_cur_download)

    def _update_cur_download_slots(self, download):
        def update_cur_download():
            with self._current_download_lock:
                if download is self.current_download:
                    if download is None:
                        self.slots_label.set_text('')
                        self.maxslot_label.set_text('')
                    else:
                        self.slots_label.set_text(str(download.active_slot))
                        self.maxslot_label.set_text(str(download.max_slot))
        gobject.idle_add(update_cur_download)

    def _update_cur_source_labels(self, source):
        def update_cur_source():
            with self._current_source_lock:
                if source is self.current_source:
                    # TODO: show timeout
                    if source is None:
                        self.source_url_label.set_text('')
                        self.source_realurl_label.set_text('')
                        self.source_retries_label.set_text('')
                        self.source_wait_label.set_text('')
                        self.source_useragent_label.set_text('')
                        self.source_referrer_label.set_text('')
                        self.source_cookie_label.set_text('')
                    else:
                        if source.max_retries < 0:
                            retries_str = u"\u221E"
                        else:
                            retries_str = str(int(source.max_retries))
                        self.source_url_label.set_text(source.original_url)
                        self.source_realurl_label.set_text(source.url)
                        self.source_retries_label.set_text('{0}/{1}'.format(
                                                    source.retries,
                                                    retries_str))
                        self.source_wait_label.set_text(
                                                    str(int(source.wait_time)))
                        self.source_useragent_label.set_text(source.user_agent)
                        self.source_referrer_label.set_text(source.referrer)
                        self.source_cookie_label.set_text(source.cookie_string)
        gobject.idle_add(update_cur_source)

    def _on_download_filename_changed(self, download):
        def update_download_list():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[1] = download.filename

        gobject.idle_add(update_download_list)
        self._update_cur_download_filename(download)

    def _on_download_filesize_changed(self, download):
        def update_download_list():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[3] = download.filesize

        gobject.idle_add(update_download_list)
        self._update_cur_download_filesize(download)

    def _on_download_state_changed(self, download):
        def state_changed():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[5] = download.state
                    # if download is not loading anymore, the
                    # DownloadMeter will not check if the progress has
                    # changed. So we need to update manually.
                    if (download.state == DownloadState.paused or
                            download.state == DownloadState.cancelled or
                            download.state == DownloadState.failed or
                            download.state == DownloadState.finished):
                        self._on_download_bytes_changed(download,
                                                download.get_bytes_loaded())
                        self._on_download_speed_changed(download, 0)

        gobject.idle_add(state_changed)

    def _on_download_slots_changed(self, download):
        def update_download_list():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[8] = download.active_slot
                    row[9] = download.max_slot

        gobject.idle_add(update_download_list)
        self._update_cur_download_slots(download)

    def _on_download_retries_changed(self, download):
        def retries_changed():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    retries, max_retries = download.get_retries()
                    row[6] = retries
                    row[7] = max_retries

        gobject.idle_add(retries_changed)

    def _on_download_source_added(self, download, source):
        def update_cur_download():
            with self._current_download_lock:
                if download is self.current_download:
                    with self._sources_lock:
                        self._add_source(source)
        source.url_changed_event.add_listener(self._update_cur_source_labels)
        source.retries_changed_event.add_listener(
                                                self._update_cur_source_labels)
        gobject.idle_add(update_cur_download)

    def _on_download_bytes_changed(self, download, bytes):
        def download_bytes_changed():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[2] = bytes
                    if download.filesize is not None:
                        row[4] = self._download_progress(download, bytes)

        gobject.idle_add(download_bytes_changed)
        self._update_cur_download_progress(download)

    def _on_download_speed_changed(self, download, speed):
        def download_bytes_changed():
            with self._download_list_lock:
                row = self._get_download_row(download)
                if row is not None:
                    row[10] = speed

        gobject.idle_add(download_bytes_changed)

    def _on_downloadlog_message_added(self, log, message):
        def downloadlog_message_added():
            with self._current_download_lock:
                if (self.current_download is not None and
                        self.current_download.log is log):
                    self._log_lock.acquire()
                    self._add_log_message(message)
                    self._log_lock.release()

        gobject.idle_add(downloadlog_message_added)

    def _on_speed_changed(self, speed):
        self.speed_meter.add_value(speed)

    def _on_log_view_size_allocate(self, widget, event, data=None):
        # auto-scroll download log
        adj = self.log_scrolled.get_vadjustment()
        adj.set_value(adj.upper - adj.page_size)

    def _get_selected_download(self):
        tree_selection = self.download_view.get_selection()
        model, iter = tree_selection.get_selected()
        if iter is None:
            return None
        return model.get_value(iter, 0)

    def _get_selected_source(self):
        tree_selection = self.sources_view.get_selection()
        model, iter = tree_selection.get_selected()
        if iter is None:
            return None
        return model.get_value(iter, 0)

    def _on_download_view_cursor_changed(self, widget=None):
        with self._download_list_lock:
            with self._current_download_lock:
                self.current_download = self._get_selected_download()

                with self._log_lock:
                    self.log_store.clear()
                    if self.current_download is not None:
                        for message in (self.current_download.
                                        log.get_copy_of_messages()):
                            self._add_log_message(message)

                with self._current_source_lock:
                    self.current_source = None
                    self._update_cur_source_labels(None)

                with self._sources_lock:
                    self.sources_store.clear()
                    if self.current_download is not None:
                        for source in (self.current_download.
                                        get_copy_of_sources()):
                            self._add_source(source)

                if self.current_download is not None:
                    self.folder_label.set_text(self.current_download.target_folder)
                else:
                    self.folder_label.set_text('')
                self._update_cur_download_filename(self.current_download)
                self._update_cur_download_filesize(self.current_download)
                self._update_cur_download_slots(self.current_download)
                self._update_cur_download_progress(self.current_download)

    def on_sources_view_cursor_changed(self, widget=None):
        with self._sources_lock:
            with self._current_source_lock:
                self.current_source = self._get_selected_source()
                self._update_cur_source_labels(self.current_source)

    def _on_add_download(self, ndw):
        s = Source(url=ndw.url, max_redirects=ndw.redirects,
                        max_retries=ndw.retries, wait_time=ndw.wait_retries)
        s.url_changed_event.add_listener(self._update_cur_source_labels)
        s.retries_changed_event.add_listener(self._update_cur_source_labels)

        s.timeout = ndw.timeout
        s.user_agent = ndw.user_agent
        s.referrer = ndw.referrer
        s.set_cookie_string(ndw.cookie)

        d = Download(ndw.slots, s, ndw.target_folder)
        d.log.message_added_event.add_listener(
                                            self._on_downloadlog_message_added)
        d.status_changed_event.add_listener(self._on_download_state_changed)
        d.filename_changed_event.add_listener(
                                            self._on_download_filename_changed)
        d.filesize_changed_event.add_listener(
                                            self._on_download_filesize_changed)
        d.slots_changed_event.add_listener(self._on_download_slots_changed)
        d.retries_changed_event.add_listener(self._on_download_retries_changed)
        d.source_added_event.add_listener(self._on_download_source_added)

        d.chunk_size = ndw.chunk_size

        if ndw.state_paused:
            d.pause()
        self.manager.add_download(d)

    def on_add_download_action_activate(self, widget):
        ndw = NewDownloadWindow()
        ndw.add_download_event.add_listener(self._on_add_download)
        ndw.show()

    def on_remove_download_action_activate(self, widget):
        def with_locks(function):
            # used to minimize indentations
            with self._download_list_lock:
                with self._current_download_lock:
                    function()

        def remove_selected_download():
            if self.current_download is not None:
                removed = self.manager.remove_download(self.current_download)
                if removed:
                    # remove download from store
                    for row in self.download_store:
                        if row[0] is self.current_download:
                            self.download_store.remove(row.iter)
                            break
                    # remove listener
                    (self.current_download.log.message_added_event.
                        remove_listener(self._on_downloadlog_message_added))
                    self.current_download.status_changed_event.remove_listener(
                                            self._on_download_state_changed)
                    (self.current_download.filename_changed_event.
                        remove_listener(self._on_download_filename_changed))
                    (self.current_download.filesize_changed_event.
                        remove_listener(self._on_download_filesize_changed))
                    self.current_download.slots_changed_event.remove_listener(
                                            self._on_download_slots_changed)
                    (self.current_download.retries_changed_event.
                        remove_listener(self._on_download_retries_changed))
                    self.current_download.source_added_event.remove_listener(
                                                self._on_download_source_added)
                    self._on_download_view_cursor_changed()
                else:
                    dlg = gtk.MessageDialog(parent=self.window,
                            type=gtk.MESSAGE_ERROR,
                            buttons=gtk.BUTTONS_OK,
                            message_format='Could not delete download! '+
                                        'Be sure that download is not running')
                    result = dlg.run()
                    dlg.destroy()

        with_locks(remove_selected_download)

    def on_download_view_key_press_event(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)

        if keyname == 'Delete':
            self.remove_download_action.activate()

    def on_start_download_action_activate(self, widget):
        download = self._get_selected_download()
        if download is None:
                return
        download.ready()

    def on_pause_download_action_activate(self, widget):
        download = self._get_selected_download()
        if download is None:
                return
        download.pause()

    def on_cancel_download_action_activate(self, widget):
        download = self._get_selected_download()
        if download is None:
                return

        dlg = gtk.MessageDialog(parent=self.window,
                    type=gtk.MESSAGE_WARNING,
                    buttons=gtk.BUTTONS_YES_NO,
                    message_format='Previously loaded data will be lost! ' +
                            'Are you shure you want to cancel the download?')
        result = dlg.run()
        dlg.destroy()
        if result == gtk.RESPONSE_YES:
            download.cancel()

    def on_add_source_action_activate(self, widget):
        with self._current_download_lock:
            if self.current_download is not None:
                nsw = NewSourceWindow(self.current_download)
                nsw.show()

    def on_remove_source_action_activate(self, widget):
        def with_locks(function):
            # used to minimize indentations
            with self._current_download_lock:
                with self._sources_lock:
                    with self._current_source_lock:
                        function()

        def remove_selected_source():
            if (self.current_download is not None and
                    self.current_source is not None):
                removed = self.current_download.remove_source(
                                                        self.current_source)
                if removed:
                    # remove source from store
                    for row in self.sources_store:
                        if row[0] is self.current_source:
                            self.sources_store.remove(row.iter)
                            break
                    # remove listener
                    (self.current_source.url_changed_event.remove_listener(
                                            self._update_cur_source_labels))
                    (self.current_source.retries_changed_event.remove_listener(
                                            self._update_cur_source_labels))
                    self.on_sources_view_cursor_changed()
                else:
                    dlg = gtk.MessageDialog(parent=self.window,
                            type=gtk.MESSAGE_ERROR,
                            buttons=gtk.BUTTONS_OK,
                            message_format='You cannot delete this source!')
                    result = dlg.run()
                    dlg.destroy()

        with_locks(remove_selected_source)

    def on_info_action_activate(self, widget):
        response = self.aboutdialog.run()
        if (response == gtk.RESPONSE_DELETE_EVENT or
                response == gtk.RESPONSE_CANCEL):
            self.aboutdialog.hide()

    def _update_colors(self):
        # Speed Meter
        self.speed_meter.background_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.background', '#ffffff'))
        self.speed_meter.gradient1_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.gradient1', '#FFE359'))
        self.speed_meter.gradient2_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.gradient2', '#FFBA00'))
        self.speed_meter.border_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.border', '#EAAA00'))
        self.speed_meter.grid_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.grid', '#000000'))
        self.speed_meter.text_color = gtk.gdk.Color(settings.get('gui.main_window.speed_meter.text', '#000000'))

        self.speed_meter.background_alpha = settings.get_int('gui.main_window.speed_meter.background_alpha', 65535)
        self.speed_meter.gradient1_alpha = settings.get_int('gui.main_window.speed_meter.gradient1_alpha', 65535)
        self.speed_meter.gradient2_alpha = settings.get_int('gui.main_window.speed_meter.gradient2_alpha', 65535)
        self.speed_meter.border_alpha = settings.get_int('gui.main_window.speed_meter.border_alpha', 65535)
        self.speed_meter.grid_alpha = settings.get_int('gui.main_window.speed_meter.grid_alpha', 6553)
        self.speed_meter.text_alpha = settings.get_int('gui.main_window.speed_meter.text_alpha', 65535)

        self.speed_meter.queue_draw()

        # chunk progress
        self.chunk_progress.background_color = gtk.gdk.Color(settings.get('gui.main_window.chunk_progress.background', '#ffffff'))
        self.chunk_progress.gradient1_color = gtk.gdk.Color(settings.get('gui.main_window.chunk_progress.gradient1', '#739ECE'))
        self.chunk_progress.gradient2_color = gtk.gdk.Color(settings.get('gui.main_window.chunk_progress.gradient2', '#ADC7E5'))
        self.chunk_progress.border_color = gtk.gdk.Color(settings.get('gui.main_window.chunk_progress.border', '#333333'))

        self.chunk_progress.background_alpha = settings.get_int('gui.main_window.chunk_progress.background_alpha', 65535)
        self.chunk_progress.gradient1_alpha = settings.get_int('gui.main_window.chunk_progress.gradient1_alpha', 65535)
        self.chunk_progress.gradient2_alpha = settings.get_int('gui.main_window.chunk_progress.gradient2_alpha', 65535)
        self.chunk_progress.border_alpha = settings.get_int('gui.main_window.chunk_progress.border_alpha', 65535)

        self.chunk_progress.queue_draw()

    def on_settings_action_activate(self, widget):
        SettingsDialog().run()
        self._update_colors()

    def on_quit_action_activate(self, widget):
        if not self._quit():
            self.window.destroy()  # on_main_window_hide will be called

    def on_parallel_spin_value_changed(self, widget):
        self.manager.set_max_parallel_downloads(self.parallel_spin.get_value())

    def on_main_window_delete_event(self, widget, event, data=None):
        return self._quit()  # on_main_window_hide will be called

    def on_main_window_hide(self, widget, data=None):
        self.manager.quit()

        # save window settings
        x, y = self.window.window.get_root_origin()
        w, h = self.window.get_size()
        settings.set('gui.main_window.x', x)
        settings.set('gui.main_window.y', y)
        settings.set('gui.main_window.width', w)
        settings.set('gui.main_window.height', h)

        settings.set('gui.main_window.progress_width', self.progress_column.get_width())
        settings.set('gui.main_window.filename_width', self.filename_column.get_width())
        settings.set('gui.main_window.state_width', self.state_column.get_width())
        settings.set('gui.main_window.slots_width', self.slots_column.get_width())
        settings.set('gui.main_window.retries_width', self.retries_column.get_width())
        settings.set('gui.main_window.speed_width', self.speed_column.get_width())
        settings.set('gui.main_window.timeleft_width', self.timeleft_column.get_width())

        # save downloads
        downloads_file.set('downloads', self.manager.get_downloads_as_list())

        gtk.main_quit()
