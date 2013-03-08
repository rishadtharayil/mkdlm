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

"""The log-module contains two classes: Log and MessageType

Log: This is a log for messages.
MessageType: This class can be used to specify the type of a message.
"""

from datetime import datetime
from threading import Lock

from event.eventlistener import EventListener


class MessageType:
    """Used to specify the type of a message."""

    info = 0
    error = 1
    warning = 2


class Log:
    """A collection of log-messages.

    Each message will be logged with the current datetime, MessageType
    and name.
    Listeners can be added that will be called when a new message was
    added.

    Public instance variables:
    message_added_event -- An event.eventlistener.EventListener object.
                           The event is signalled when a new message was
                           added to the log.
                           The listeners are called with two parameters.
                           The first parameter is the log-object. The
                           second parameter is the new message. It is a
                           tuple of 4 values: The MessageType, datetime,
                           name and the message itself.
    """

    def __init__(self):
        """Initialize the Log."""
        self._messages_lock = Lock()
        self._messages = []
        self.message_added_event = EventListener()

    def add_log_entry(self, type, name, message):
        """Add a new message to the log.

        type -- the MessageType of the log entry
        name -- the name of the owner of the message
        message -- the message to add
        """
        new_message = (type, datetime.today(), name, message)
        with self._messages_lock:
            self._messages.append(new_message)
            self.message_added_event.signal(self, new_message)

    def get_copy_of_messages(self):
        with self._messages_lock:
            copy = self._messages[:]
        return copy
