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

import pygtk
pygtk.require("2.0")
import gtk

from globals import settings
from gui.chunkprogress import ChunkProgress
from gui.meter import Meter


class SettingsDialog:
    def __init__(self):
        builder = gtk.Builder()
        glade = join(dirname(realpath(__file__)), 'settings_dialog.glade')
        builder.add_from_file(glade)

        self.dialog = builder.get_object("settings_dialog")
        self.target_folder_button = builder.get_object("target_folder_button")
        self.slot_spin = builder.get_object("slot_spin")
        self.retries_spin = builder.get_object("retries_spin")
        self.wait_spin = builder.get_object("wait_spin")
        self.redirects_spin = builder.get_object("redirects_spin")
        self.useragent_entry = builder.get_object("useragent_entry")
        self.chunksize_spin = builder.get_object("chunksize_spin")
        self.timeout_spin = builder.get_object('timeout_spin')
        self.parallel_spin = builder.get_object('parallel_spin')

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

        # For color-previews
        self.preview_box = builder.get_object("preview_box")

        # Speed Meter Preview
        self.meter = Meter()

        self.meter.add_value(1)
        self.meter.add_value(2)
        self.meter.add_value(2)
        self.meter.add_value(6)
        self.meter.add_value(7)
        self.meter.add_value(10)
        self.meter.add_value(8)
        for i in range(100):
            self.meter.add_value(8)
        self.meter.add_value(5)
        self.meter.add_value(3)
        self.meter.add_value(1)
        for i in range(20):
            self.meter.add_value(7)

        self.preview_box.pack_start(self.meter, True, True, 0)
        self.meter.show_all()

        # Chunk Progress Preview
        self.chunk_progress = ChunkProgress()
        self.chunk_progress.set_chunks([(0, 10), (25, 25), (85, 15)], 100)
        self.preview_box.pack_start(self.chunk_progress, True, True, 0)
        self.chunk_progress.show_all()

        # Speed Meter Colors
        self.speed_background_color = builder.get_object('speed_background_color')
        self.speed_grid_color = builder.get_object('speed_grid_color')
        self.speed_border_color = builder.get_object('speed_border_color')
        self.speed_gradient1_color = builder.get_object('speed_gradient1_color')
        self.speed_gradient2_color = builder.get_object('speed_gradient2_color')
        self.speed_text_color = builder.get_object('speed_text_color')

        # Chunk Progress Colors
        self.slot_background_color = builder.get_object('slot_background_color')
        self.slot_border_color = builder.get_object('slot_border_color')
        self.slot_gradient1_color = builder.get_object('slot_gradient1_color')
        self.slot_gradient2_color = builder.get_object('slot_gradient2_color')

        # default values
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
        self.parallel_spin.set_value(
                    settings.get_int('core.manager.parallel_downloads', 1))
        self.useragent_entry.set_text(
                    settings.get('core.new_source.user_agent',
                        'Mozilla/5.0 (X11; U; Linux i686; de; rv:1.9.2.13) ' +
                        'Gecko/20101203 Firefox/3.6.13'))

        folder = settings.get('core.new_download.target_folder')
        if folder is not None:
            self.target_folder_button.set_current_folder(folder)

        # default values: speed meter
        self.speed_background_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.background',
                                    '#ffffff')))
        self.speed_grid_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.grid',
                                    '#000000')))
        self.speed_border_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.border',
                                    '#EAAA00')))
        self.speed_gradient1_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.gradient1',
                                    '#FFE359')))
        self.speed_gradient2_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.gradient2',
                                    '#FFBA00')))
        self.speed_text_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.speed_meter.text',
                                    '#000000')))

        self.speed_background_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.background_alpha',
                                    65535))
        self.speed_grid_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.grid_alpha',
                                    6553))
        self.speed_border_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.border_alpha',
                                    65535))
        self.speed_gradient1_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.gradient1_alpha',
                                    65535))
        self.speed_gradient2_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.gradient2_alpha',
                                    65535))
        self.speed_text_color.set_alpha(
                    settings.get_int('gui.main_window.speed_meter.text_alpha',
                                    65535))

        # default values: slot view / chunk progress
        self.slot_background_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.chunk_progress.background',
                                    '#ffffff')))
        self.slot_border_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.chunk_progress.border',
                                    '#333333')))
        self.slot_gradient1_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.chunk_progress.gradient1',
                                    '#739ECE')))
        self.slot_gradient2_color.set_color(gtk.gdk.Color(
                    settings.get('gui.main_window.chunk_progress.gradient2',
                                    '#ADC7E5')))

        self.slot_background_color.set_alpha(
                    settings.get_int('gui.main_window.chunk_progress.background_alpha',
                                    65535))
        self.slot_border_color.set_alpha(
                    settings.get_int('gui.main_window.chunk_progress.border_alpha',
                                    65535))
        self.slot_gradient1_color.set_alpha(
                    settings.get_int('gui.main_window.chunk_progress.gradient1_alpha',
                                    65535))
        self.slot_gradient2_color.set_alpha(
                    settings.get_int('gui.main_window.chunk_progress.gradient2_alpha',
                                    65535))


        # store values of widgets in instance variables
        self._update_data()

        builder.connect_signals(self)

    def _update_colors(self):
        # Speed Meter
        self.speed_background = self.speed_background_color.get_color()
        self.speed_grid = self.speed_grid_color.get_color()
        self.speed_border = self.speed_border_color.get_color()
        self.speed_gradient1 = self.speed_gradient1_color.get_color()
        self.speed_gradient2 = self.speed_gradient2_color.get_color()
        self.speed_text = self.speed_text_color.get_color()

        self.speed_background_alpha = self.speed_background_color.get_alpha()
        self.speed_grid_alpha = self.speed_grid_color.get_alpha()
        self.speed_border_alpha = self.speed_border_color.get_alpha()
        self.speed_gradient1_alpha = self.speed_gradient1_color.get_alpha()
        self.speed_gradient2_alpha = self.speed_gradient2_color.get_alpha()
        self.speed_text_alpha = self.speed_text_color.get_alpha()

        # chunk progress
        self.slot_background = self.slot_background_color.get_color()
        self.slot_border = self.slot_border_color.get_color()
        self.slot_gradient1 = self.slot_gradient1_color.get_color()
        self.slot_gradient2 = self.slot_gradient2_color.get_color()

        self.slot_background_alpha = self.slot_background_color.get_alpha()
        self.slot_border_alpha = self.slot_border_color.get_alpha()
        self.slot_gradient1_alpha = self.slot_gradient1_color.get_alpha()
        self.slot_gradient2_alpha = self.slot_gradient2_color.get_alpha()

        # Update preview: Speed Meter
        self.meter.background_color = self.speed_background
        self.meter.gradient1_color = self.speed_gradient1
        self.meter.gradient2_color = self.speed_gradient2
        self.meter.border_color = self.speed_border
        self.meter.grid_color = self.speed_grid
        self.meter.text_color = self.speed_text

        self.meter.background_alpha = self.speed_background_alpha
        self.meter.gradient1_alpha = self.speed_gradient1_alpha
        self.meter.gradient2_alpha = self.speed_gradient2_alpha
        self.meter.border_alpha = self.speed_border_alpha
        self.meter.grid_alpha = self.speed_grid_alpha
        self.meter.text_alpha = self.speed_text_alpha

        self.meter.queue_draw()

        # Update preview: chunk progress
        self.chunk_progress.background_color = self.slot_background
        self.chunk_progress.gradient1_color = self.slot_gradient1
        self.chunk_progress.gradient2_color = self.slot_gradient2
        self.chunk_progress.border_color = self.slot_border

        self.chunk_progress.background_alpha = self.slot_background_alpha
        self.chunk_progress.gradient1_alpha = self.slot_gradient1_alpha
        self.chunk_progress.gradient2_alpha = self.slot_gradient2_alpha
        self.chunk_progress.border_alpha = self.slot_border_alpha

        self.chunk_progress.queue_draw()

    def _update_data(self):
        self.target_folder = self.target_folder_button.get_filename()
        self.slots = self.slot_spin.get_value()
        self.retries = self.retries_spin.get_value()
        self.wait_retries = self.wait_spin.get_value()
        self.redirects = self.redirects_spin.get_value()
        self.user_agent = self.useragent_entry.get_text()
        self.chunk_size = self.chunksize_spin.get_value()
        self.timeout = self.timeout_spin.get_value()
        self.parallel_downloads = self.parallel_spin.get_value()
        self._update_colors()

    def run(self):
        ret = self.dialog.run()
        if ret != gtk.RESPONSE_DELETE_EVENT:
            self._update_data()

            settings.set('core.new_download.slots', self.slots)
            settings.set('core.new_source.retries', self.retries)
            settings.set('core.new_source.wait', self.wait_retries)
            settings.set('core.new_source.redirects', self.redirects)
            settings.set('core.new_download.chunksize', self.chunk_size)
            settings.set('core.new_source.timeout', self.timeout)
            settings.set('core.new_source.user_agent', self.user_agent)
            settings.set('core.new_download.target_folder', self.target_folder)
            settings.set('core.manager.parallel_downloads',
                            self.parallel_downloads)

            # Speed Meter Colors/Alphas
            settings.set('gui.main_window.speed_meter.background',
                                    str(self.speed_background))
            settings.set('gui.main_window.speed_meter.grid',
                                    str(self.speed_grid))
            settings.set('gui.main_window.speed_meter.border',
                                    str(self.speed_border))
            settings.set('gui.main_window.speed_meter.gradient1',
                                    str(self.speed_gradient1))
            settings.set('gui.main_window.speed_meter.gradient2',
                                    str(self.speed_gradient2))
            settings.set('gui.main_window.speed_meter.text',
                                    str(self.speed_text))

            settings.set('gui.main_window.speed_meter.background_alpha',
                                    self.speed_background_alpha)
            settings.set('gui.main_window.speed_meter.grid_alpha',
                                    self.speed_grid_alpha)
            settings.set('gui.main_window.speed_meter.border_alpha',
                                    self.speed_border_alpha)
            settings.set('gui.main_window.speed_meter.gradient1_alpha',
                                    self.speed_gradient1_alpha)
            settings.set('gui.main_window.speed_meter.gradient2_alpha',
                                    self.speed_gradient2_alpha)
            settings.set('gui.main_window.speed_meter.text_alpha',
                                    self.speed_text_alpha)

            # Chunk Progress Colors/Alphas
            settings.set('gui.main_window.chunk_progress.background',
                                    str(self.slot_background))
            settings.set('gui.main_window.chunk_progress.border',
                                    str(self.slot_border))
            settings.set('gui.main_window.chunk_progress.gradient1',
                                    str(self.slot_gradient1))
            settings.set('gui.main_window.chunk_progress.gradient2',
                                    str(self.slot_gradient2))

            settings.set('gui.main_window.chunk_progress.background_alpha',
                                    self.slot_background_alpha)
            settings.set('gui.main_window.chunk_progress.border_alpha',
                                    self.slot_border_alpha)
            settings.set('gui.main_window.chunk_progress.gradient1_alpha',
                                    self.slot_gradient1_alpha)
            settings.set('gui.main_window.chunk_progress.gradient2_alpha',
                                    self.slot_gradient2_alpha)

            settings.save()

        self.dialog.destroy()

    def on_speed_color_set(self, widget):
        self._update_colors()
