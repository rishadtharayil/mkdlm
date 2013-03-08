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
from threading import Lock

import cairo
import gtk

from gui.simpledrawingarea import SimpleDrawingArea


class ChunkProgress(SimpleDrawingArea):
    def __init__(self):
        self.background_color = gtk.gdk.Color('#fff')
        self.gradient1_color = gtk.gdk.Color('#739ECE')
        self.gradient2_color = gtk.gdk.Color('#ADC7E5')
        self.border_color = gtk.gdk.Color('#333333')

        self.background_alpha = 65535
        self.gradient1_alpha = 65535
        self.gradient2_alpha = 65535
        self.border_alpha = 65535

        self._chunks = []
        self._size = 0.0
        self._lock = Lock()
        SimpleDrawingArea.__init__(self)
        self.connect("expose-event", self.expose)
        self.set_size_request(100, 15)

    def set_chunks(self, chunks, size):
        with self._lock:
            self._chunks = chunks
            if size is None:
                self._size = 0.0
            else:
                self._size = float(size)
        self.queue_draw()

    def expose(self, widget, event):
        self.context = widget.window.cairo_create()

        # clip region for expose event
        self.context.rectangle(event.area.x, event.area.y,
                               event.area.width, event.area.height)
        self.context.clip()
        self._redraw(self.context)
        return False

    def _redraw(self, context):
        with self._lock:
            x, y, width, height = self.get_allocation()

            # background
            self.round_rectangle(context, 0.5, 0.5, width, height, 3)
            context.set_source_rgba(*self.get_rgba(self.background_color,
                                                    self.background_alpha))
            context.fill_preserve()
            context.clip()

            if self._size > 0.0:
                factor = width / self._size
                for (offset, length) in self._chunks:
                    x = offset * factor
                    w = length * factor
                    context.rectangle(x, 0, w, height)

                g = cairo.LinearGradient(0, 0, 0, height)
                g.add_color_stop_rgba(1, *self.get_rgba(self.gradient1_color,
                                                    self.gradient1_alpha))
                g.add_color_stop_rgba(0, *self.get_rgba(self.gradient2_color,
                                                    self.gradient2_alpha))
                context.set_source(g)
                context.fill()

            # border
            self.round_rectangle(context, 0.5, 0.5, width, height, 3)
            context.set_line_width(1)
            context.set_source_rgba(*self.get_rgba(self.border_color,
                                                    self.border_alpha))
            context.stroke()
