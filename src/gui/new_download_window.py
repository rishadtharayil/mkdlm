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
from urlparse import urlparse

import pygtk
pygtk.require("2.0")
import gtk

from dlm.source import Source
from event.eventlistener import EventListener
from globals import settings

class NewDownloadWindow:
    def __init__(self, url=''):
        builder = gtk.Builder()
        glade = join(dirname(realpath(__file__)), 'new_download_window.glade')
        builder.add_from_file(glade)

        self.window = builder.get_object("new_download_window")
        self.url_entry = builder.get_object("url_entry")
        self.target_folder_button = builder.get_object("target_folder_button")
        self.start_radio = builder.get_object("start_radio")
        self.paused_radio = builder.get_object("paused_radio")
        self.slot_spin = builder.get_object("slot_spin")
        self.retries_spin = builder.get_object("retries_spin")
        self.wait_spin = builder.get_object("wait_spin")
        self.redirects_spin = builder.get_object("redirects_spin")
        self.useragent_entry = builder.get_object("useragent_entry")
        self.referrer_entry = builder.get_object("referrer_entry")
        self.cookie_entry = builder.get_object("cookie_entry")
        self.chunksize_spin = builder.get_object("chunksize_spin")
        self.timeout_spin = builder.get_object('timeout_spin')

        def spin_output(spin):
            digits = int(spin.props.digits)
            value = spin.props.value
            if value < 0:
                spin.props.text = u"\u221E"
            else:
                spin.props.text = '{0:.{1}f}'.format(value, digits)
            return True
        self.retries_spin.connect('output', spin_output)

        def spin_input(spin, new_value):
            text = spin.get_text()
            if text == u"\u221E":
                value = -1
            else:
                try:
                    value = float(text)
                except ValueError:
                    return -1
            p = ctypes.c_double.from_address(hash(new_value))
            p.value = value
            return True
        self.retries_spin.connect('input', spin_input)

        # default values
        self.url_entry.set_text(url)
        self.slot_spin.set_value(
                    settings.get_float('core.new_download.slots', 3))
        self.retries_spin.set_value(
                    settings.get_float('core.new_source.retries', 5))
        self.wait_spin.set_value(
                    settings.get_float('core.new_source.wait', 10))
        self.redirects_spin.set_value(
                    settings.get_float('core.new_source.redirects', 3))
        self.chunksize_spin.set_value(
                    settings.get_float('core.new_download.chunksize', 2097152))
        self.timeout_spin.set_value(
                    settings.get_float('core.new_source.timeout', 5))
        self.useragent_entry.set_text(
                    settings.get('core.new_source.user_agent',
                        'Mozilla/5.0 (X11; U; Linux i686; de; rv:1.9.2.13) ' +
                        'Gecko/20101203 Firefox/3.6.13'))

        folder = settings.get('core.new_download.target_folder')
        if folder is not None:
            self.target_folder_button.set_current_folder(folder)

        # store values of widgets in instance variables
        self._update_data()

        self.add_download_event = EventListener()

        builder.connect_signals(self)

    def _update_data(self):
        self.url = self.url_entry.get_text()
        self.target_folder = self.target_folder_button.get_filename()
        self.state_start = self.start_radio.get_active()
        self.state_paused = self.paused_radio.get_active()
        self.slots = self.slot_spin.get_value()
        self.retries = self.retries_spin.get_value()
        self.wait_retries = self.wait_spin.get_value()
        self.redirects = self.redirects_spin.get_value()
        self.user_agent = self.useragent_entry.get_text()
        self.referrer = self.referrer_entry.get_text()
        self.cookie = self.cookie_entry.get_text()
        self.chunk_size = self.chunksize_spin.get_value()
        self.timeout = self.timeout_spin.get_value()

    def show(self):
        self.window.show()

    def on_cancel_button_clicked(self, widget):
        self.window.destroy()

    def on_add_button_clicked(self, widget):
        self._update_data()

        # is url valid?
        url_parts = urlparse(self.url)
        if (url_parts.scheme != 'http' and url_parts.scheme != 'https' and
                url_parts.scheme != 'ftp'):
            dlg = gtk.MessageDialog(parent=self.window, type=gtk.MESSAGE_ERROR,
                            buttons=gtk.BUTTONS_OK,
                            message_format='The URL you entered is invalid!')
            result = dlg.run()
            dlg.destroy()
            return

        # is cookie string valid?
        if (self.cookie != '' and
                not Source.is_cookie_string_valid(self.cookie)):
            dlg = gtk.MessageDialog(parent=self.window, type=gtk.MESSAGE_ERROR,
                    buttons=gtk.BUTTONS_OK,
                    message_format='The cookie string you entered is invalid!')
            result = dlg.run()
            dlg.destroy()
            return

        self.add_download_event.signal(self)
        self.window.destroy()
