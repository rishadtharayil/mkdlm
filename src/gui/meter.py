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
from collections import deque
from threading import Lock

import gtk
import cairo

from gui.simpledrawingarea import SimpleDrawingArea


class ToolMeter(gtk.ToolItem):
    def __init__(self):
        gtk.ToolItem.__init__(self)
        self.meter = Meter()
        self.add(self.meter)
        self.set_expand(True)


class Meter(SimpleDrawingArea):
    def __init__(self):
        self.background_color = gtk.gdk.Color('#fff')
        self.gradient1_color = gtk.gdk.Color('#FFE359')
        self.gradient2_color = gtk.gdk.Color('#FFBA00')
        self.border_color = gtk.gdk.Color('#EAAA00')
        self.grid_color = gtk.gdk.Color('#000')
        self.text_color = gtk.gdk.Color('#000')

        self.background_alpha = 65535
        self.gradient1_alpha = 65535
        self.gradient2_alpha = 65535
        self.border_alpha = 65535
        self.grid_alpha = 6553
        self.text_alpha = 65535

        self.x_step = 1
        self.text_callback = lambda a, b, c: 'Text'
        self.avg_steps = 60

        width = gtk.gdk.screen_get_default().get_width()
        self.max_values = width

        self._values = deque([])
        self._max_value = 0
        self._lock = Lock()

        SimpleDrawingArea.__init__(self)
        self.connect("expose-event", self.expose)
        self.set_size_request(100, 40)

    def add_value(self, value):
        with self._lock:
            self._values.appendleft(value)
            if value > self._max_value:
                self._max_value = float(value)
            if len(self._values) > self.max_values:
                self._values.pop()
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

            context.set_line_width(1)

            # background
            self.round_rectangle(context, 0, 0, width, height, 3)
            context.set_source_rgba(*self.get_rgba(self.background_color,
                                                    self.background_alpha))
            context.fill_preserve()
            context.clip()

            if self._max_value == 0:
                factor = 0
            else:
                factor = height / self._max_value

            # diagram
            cx = width
            context.move_to(cx, height)

            for value in self._values:
                context.line_to(cx, height - factor * value)
                if cx <= 0:
                    break
                cx -= self.x_step

            context.line_to(cx, height)
            context.close_path()

            g = cairo.LinearGradient(0, 0, 0, height)
            g.add_color_stop_rgba(0, *self.get_rgba(self.gradient1_color,
                                                    self.gradient1_alpha))
            g.add_color_stop_rgba(1, *self.get_rgba(self.gradient2_color,
                                                    self.gradient2_alpha))
            context.set_source(g)
            context.fill_preserve()

            context.set_source_rgba(*self.get_rgba(self.border_color,
                                                    self.border_alpha))
            context.set_line_join(cairo.LINE_JOIN_ROUND)
            context.stroke()

            steps = min(len(self._values), self.avg_steps)
            tmp = 0
            for i in range(steps):
                tmp += self._values[i]
            if steps > 0:
                avg = tmp / steps
            else:
                avg = 0

            if len(self._values) > 0:
                text = self.text_callback(self._values[0], self._max_value, avg)
            else:
                text = self.text_callback(0, 0, 0)

            # grid
            context.set_source_rgba(*self.get_rgba(self.grid_color,
                                                    self.grid_alpha))
            cx = width - 60 + 0.5
            while cx >= 0:
                context.move_to(cx, 0)
                context.line_to(cx, height)
                context.stroke()
                cx -= 60

            context.set_source_rgba(*self.get_rgba(self.text_color,
                                                    self.text_alpha))
            #context.select_font_face("Purisa", cairo.FONT_SLANT_NORMAL,
            #    cairo.FONT_WEIGHT_NORMAL)
            context.set_font_size(11)
            self.show_right_aligned_text(context, width, height, text)

