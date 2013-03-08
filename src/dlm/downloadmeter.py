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
from threading import Thread
from time import time, sleep

from download import DownloadState
from event.eventlistener import EventListener


class DownloadMeter(Thread):
    def __init__(self, manager):
        self.download_bytes_changed_event = EventListener()
        self.download_speed_changed_event = EventListener()
        self.speed_changed_event = EventListener()

        self._manager = manager
        self._running = True
        Thread.__init__(self)

    def stop(self):
        self._running = False
        self.join()

    def run(self):
        latest_bytes = {}
        latest_speed = {}
        changed_bytes = []
        changed_speed = []

        while self._running:
            global_speed = 0
            del changed_bytes[:]
            del changed_speed[:]
            downloads = self._manager.get_download_list_copy()

            for download in downloads:
                if download.state != DownloadState.loading:
                    if download in latest_bytes:
                        del latest_bytes[download]
                    if download in latest_speed:
                        del latest_speed[download]
                    continue

                # TODO: better use monotonic time
                now = time()
                if download in latest_bytes:
                    t, bytes = latest_bytes[download]
                    speed = None
                    if download in latest_speed:
                        speed = latest_speed[download]

                    new_bytes = download.get_bytes_loaded()
                    byte_diff = new_bytes - bytes
                    time_diff = now - t
                    new_speed = byte_diff / time_diff

                    if new_bytes != bytes:
                        changed_bytes.append((download, new_bytes))

                    if speed is None or new_speed != speed:
                        changed_speed.append((download, new_speed))

                    latest_bytes[download] = (now, new_bytes)
                    latest_speed[download] = new_speed
                    global_speed += new_speed
                else:
                    changed_bytes.append((download,
                                                download.get_bytes_loaded()))
                    latest_bytes[download] = (now,
                                                download.get_bytes_loaded())

            for (download, bytes) in changed_bytes:
                self.download_bytes_changed_event.signal(download, bytes)

            for (download, speed) in changed_speed:
                self.download_speed_changed_event.signal(download, speed)

            self.speed_changed_event.signal(global_speed)
            sleep(1)

