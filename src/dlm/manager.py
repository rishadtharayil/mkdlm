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
from threading import Lock, RLock
from time import sleep

from download import DownloadState, Download
from downloadmeter import DownloadMeter
from event.eventlistener import EventListener


class Manager:
    def __init__(self):
        self._download_list_lock = RLock()
        self._downloads = []
        self.download_added_event = EventListener()
        self.max_parallel_downloads_changed_event = EventListener()
        self.download_meter = DownloadMeter(self)
        self.download_meter.start()
        self._active_downloads = 0
        self._quit = False
        self.set_max_parallel_downloads(1)

    def create_downloads_from_list(self, list):
        downloads = []
        for download in list:
            downloads.append(Download.create_from_dict(download))
        return downloads

    def get_downloads_as_list(self):
        downloads = []
        with self._download_list_lock:
            for download in self._downloads:
                downloads.append(download.get_as_dict())
        return downloads

    def add_download(self, download):
        download.status_changed_event.add_listener(
                                            self._on_download_status_changed)
        with self._download_list_lock:
            self._downloads.append(download)
        self.download_added_event.signal(download)
        self._update_manager()

    def remove_download(self, download):
        removed = True
        with self._download_list_lock:
            if download.is_loading() or download.is_fetching_info():
                removed = False
            else:
                try:
                    self._downloads.remove(download)
                except ValueError:
                    removed = False
                else:
                    download.status_changed_event.remove_listener(
                                            self._on_download_status_changed)
        return removed

    def quit(self):
        with self._download_list_lock:
            self._quit = True
            self.download_meter.stop()
            for download in self._downloads:
                while (download.state == DownloadState.fetching_info or
                        download.state == DownloadState.loading):
                    download.pause()
            # wait for downloads
            for download in self._downloads:
                while (download.state == DownloadState.fetching_info or
                        download.state == DownloadState.loading or
                        download.state == DownloadState.stopping):
                    sleep(0.2)


    def get_download_list_copy(self):
        with self._download_list_lock:
            copy = self._downloads[:]
        return copy

    def set_max_parallel_downloads(self, num):
        self.max_parallel_downloads = num
        self.max_parallel_downloads_changed_event.signal()
        self._update_manager()

    def _get_next_ready_download(self):
        result = None
        with self._download_list_lock:
            for download in self._downloads:
                if download.state == DownloadState.ready:
                    result = download
                    break
        return result

    def _update_active_downloads(self):
        active = 0
        with self._download_list_lock:
            for download in self._downloads:
                if (download.state == DownloadState.loading or
                        download.state == DownloadState.fetching_info):
                    active += 1
        self._active_downloads = active

    def _update_manager(self):
        with self._download_list_lock:
            self._update_active_downloads()
            if (not self._quit and
                    self._active_downloads < self.max_parallel_downloads or
                    self.max_parallel_downloads == 0):
                # we can start more downloads
                startable = (self.max_parallel_downloads -
                                self._active_downloads)
                while startable > 0 or startable < 0:
                    download = self._get_next_ready_download()
                    if download is None:
                        # no more ready downloads exist
                        break
                    download.start()
                    startable -= 1


    def _on_download_status_changed(self, download):
        self._update_manager()
