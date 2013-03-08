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
import gobject

from event.eventlistener import EventListener
from dlm.slot import InfoSlot
from dlm.source import Source
from globals import settings


class NewSourceWindow:
    def __init__(self, download, url=''):
        self.download = download

        builder = gtk.Builder()
        glade = join(dirname(realpath(__file__)), 'new_source_window.glade')
        builder.add_from_file(glade)

        self.window = builder.get_object("new_source_window")
        self.url_entry = builder.get_object("url_entry")
        self.retries_spin = builder.get_object("retries_spin")
        self.wait_spin = builder.get_object("wait_spin")
        self.redirects_spin = builder.get_object("redirects_spin")
        self.useragent_entry = builder.get_object("useragent_entry")
        self.referrer_entry = builder.get_object("referrer_entry")
        self.cookie_entry = builder.get_object("cookie_entry")
        self.timeout_spin = builder.get_object('timeout_spin')
        self.progressbar = builder.get_object('progressbar')

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
        self.retries_spin.set_value(
                    settings.get_float('core.new_source.retries', 5))
        self.wait_spin.set_value(
                    settings.get_float('core.new_source.wait', 10))
        self.redirects_spin.set_value(
                    settings.get_float('core.new_source.redirects', 3))
        self.timeout_spin.set_value(
                    settings.get_float('core.new_source.timeout', 5))
        self.useragent_entry.set_text(
                    settings.get('core.new_source.user_agent',
                        'Mozilla/5.0 (X11; U; Linux i686; de; rv:1.9.2.13) ' +
                        'Gecko/20101203 Firefox/3.6.13'))

        # store values of widgets in instance variables
        self._update_data()

        builder.connect_signals(self)

    def _update_data(self):
        self.url = self.url_entry.get_text()
        self.retries = self.retries_spin.get_value()
        self.wait_retries = self.wait_spin.get_value()
        self.redirects = self.redirects_spin.get_value()
        self.user_agent = self.useragent_entry.get_text()
        self.referrer = self.referrer_entry.get_text()
        self.cookie = self.cookie_entry.get_text()
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

        # get infos from source
        self.progressbar.show()
        self.window.set_sensitive(False)

        self.source = Source(self.url, self.redirects, 0, self.wait_retries)
        self.source.timeout = self.timeout
        self.source.user_agent = self.user_agent
        self.source.referrer = self.referrer
        self.source.set_cookie_string(self.cookie)

        self.infoslot = InfoSlot('Info Slot', self.source, None,
                            self._on_infos_fetched, self._on_infos_failed)
        self.infoslot.start()

    def _on_infos_fetched(self):
        self.infoslot.connection.close()

        def on_fetch():
            if not self.window.props.visible:
                return

            self.source.set_max_retries(self.retries)
            self.download.add_source(self.source)
            self.window.destroy()

        gobject.idle_add(on_fetch)

    def _on_infos_failed(self):
        self.infoslot.connection.close()

        def on_fail():
            if not self.window.props.visible:
                return

            self.progressbar.hide()
            self.window.set_sensitive(True)
            messages = self.infoslot.log.get_copy_of_messages()
            messages_str = ''
            for (type, time, name, message) in messages:
                messages_str += message + '\n'
            dlg = gtk.MessageDialog(parent=self.window, type=gtk.MESSAGE_ERROR,
                    buttons=gtk.BUTTONS_OK,
                    message_format='Fetching information from Source failed!' +
                                    '\n\nLog:\n{0}'.format(messages_str))
            result = dlg.run()
            dlg.destroy()

        gobject.idle_add(on_fail)
