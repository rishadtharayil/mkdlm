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
""" This module contains the TargetFile class."""

from threading import Lock


class TargetFileIOError(IOError):
    def __init__(self, e):
        IOError.__init__(self, e)


class TargetFile:
    """This class represents the target file of a download.

    It has methods to open the target file, write data synchronously
    and close the file.
    """

    def __init__(self, target_file):
        """Initialize the TargetFile-object.

        target_file -- the path of the target file
        """
        self.target_file = target_file
        self.opened_file = None
        self.write_lock = Lock()

    def open(self):
        """Open the target file for binary writing."""
        with self.write_lock:
            try:
                if self.opened_file is None:
                    # try to create file
                    open(self.target_file, "a").close()
                    # open file
                    self.opened_file = open(self.target_file, 'r+b')
            except IOError, e:
                raise TargetFileIOError(e)

    def write(self, offset, bytes):
        """Write bytes at a specified offset to the target file
        synchronously.

        offset -- the file offset
        bytes -- the bytes to write
        """
        with self.write_lock:
            try:
                self.opened_file.seek(offset)
                self.opened_file.write(bytes)
            except IOError, e:
                raise TargetFileIOError(e)

    def close(self):
        """Close the target file."""
        with self.write_lock:
            try:
                if self.opened_file is not None:
                    self.opened_file.close()
                    self.opened_file = None
            except IOError, e:
                raise TargetFileIOError(e)
