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

"""This module contains the Chunk-class.

The Chunk-class represents a part of a download-file.
"""

class Chunk:
    """A chunk is a part of a download-file.

    It specifies how many bytes from which offset should be loaded.
    It may have a parent chunk from which it is derived.
    """

    def __init__(self, parent, offset, length):
        """Initialize the Chunk.

        parent -- the parent chunk from which this chunk is derived
        offset -- the offset to start loading bytes from
        length -- how many bytes should be loaded
        """
        self.childs = []
        self.parent = parent
        self.offset = offset
        self.original_length = length
        self.length = length
        self.loaded = 0

    @staticmethod
    def create_from_dict(dict, parent=None):
        # TODO: validate values?!
        chunk = Chunk(parent, dict['offset'], dict['length'])
        chunk.original_length = dict['original_length']
        chunk.loaded = dict['loaded']
        childs = []
        for child in dict['childs']:
            childs.append(Chunk.create_from_dict(child, chunk))
        chunk.childs = childs
        return chunk

    def get_as_dict(self):
        childs = []
        for child in self.childs:
            childs.append(child.get_as_dict())
        chunk = {
            'offset': self.offset,
            'original_length': self.original_length,
            'length': self.length,
            'loaded': self.loaded,
            'childs': childs
        }
        return chunk

    def is_finished(self, slots_supported):
        """Returns True if the chunk is finished, otherwise False.

        Note: A chunk is never finished if its length is unknown (None).
        """
        if self.length is None:
            return False
        return ((slots_supported and self.loaded >= self.length) or
                (not slots_supported and
                 self.loaded >= self.original_length))

    def bytes_left(self, slots_supported):
        """Returns the number of bytes which still need to be loaded.

        Note: If the length of the chunk is unknown (None) then None is
              returned.
        """
        if self.length is None and self.original_length is None:
            return None
        elif slots_supported:
            return self.length - self.loaded
        else:
            return self.original_length - self.loaded

    def bytes_loaded(self, slots_supported):
        """Returns the number of loaded bytes."""
        if self.length is None:
            return self.loaded
        elif slots_supported and self.loaded > self.length:
            return self.length
        else:
            return self.loaded
