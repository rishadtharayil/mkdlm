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
import math

import gtk


class SimpleDrawingArea(gtk.DrawingArea):
    def __init__(self):
        gtk.DrawingArea.__init__(self)

    def round_rectangle(self, context, x, y, width, height, radius):
        context.arc(x + radius, y + radius, radius, math.pi, math.pi * 3 / 2)
        context.arc(x + width-radius-1, y + radius, radius, math.pi * 3 / 2, math.pi * 2)
        context.arc(x + width-radius-1, y + height-radius-1, radius, 0, math.pi / 2)
        context.arc(x + radius, y + height-radius-1, radius, math.pi / 2, math.pi)
        context.close_path()

    def show_right_aligned_text(self, context, x, y, text):
        # te = (xbearing, ybearing, width, height, xadvance, yadvance)
        te = context.text_extents(text)
        tx = te[0] + te[2]
        context.move_to(x - tx, y - 2)
        context.show_text(text)

    def get_rgba(self, color, alpha):
        return (float(color.red) / 65535, float(color.green) / 65535,
                float(color.blue) / 65535, float(alpha) / 65535)
