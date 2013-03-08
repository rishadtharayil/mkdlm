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

# v0.1

from os import makedirs, path

import yaml


class SettingsFileType:
    user_settings = 0

class SettingsFile:
    def __init__(self, type, program_name, filename):
        self._type = type
        self._program_name = program_name
        self._filename = filename
        self._settings = {}

    def load(self):
        file = self._get_settings_file()
        if file is None or not path.exists(file):
            return
        with open(file) as f:
            self._settings = yaml.load(f)
        if self._settings is None:
            self._settings = {}

    def save(self):
        folder = self._get_settings_folder()
        file = self._get_settings_file()
        if file is None or folder is None:
            return
        if not path.exists(folder):
            makedirs(folder)
        with open(file, "w") as f:
            yaml.dump(self._settings, f)

    def get(self, path, default=None):
        names = path.split('.')

        settings = self._settings
        for name in names:
            if name in settings:
                settings = settings[name]
            else:
                return default

        return settings

    def get_float(self, path, default=None):
        val = self.get(path)
        if val is not None:
            try:
                return float(val)
            except ValueError, e:
                pass
        return default

    def get_int(self, path, default=None):
        val = self.get(path)
        if val is not None:
            try:
                return int(val)
            except ValueError, e:
                pass
        return default

    def set(self, path, value):
        names = path.split('.')

        settings = self._settings
        for i in range(len(names)):
            name = names[i]
            if i >= len(names)-1:
                settings[name] = value
            elif name not in settings:
                settings[name] = {}
                settings = settings[name]
            else:
                settings = settings[name]

    def _get_settings_folder(self):
        if self._type == SettingsFileType.user_settings:
            dir = path.expanduser('~')

            try:
                from win32com.shell import shellcon, shell
                dir = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
            except ImportError:
                dir = path.expanduser("~")

            return path.join(dir, '.' + self._program_name)

    def _get_settings_file(self):
        folder = self._get_settings_folder()

        if folder is None:
            return None

        return path.join(folder, self._filename)


if __name__ == '__main__':
    sf = SettingsFile(SettingsFileType.user_settings, 'mkdlm', 'test')
    sf.load()

    sf.set('core.test', [1,2,3])
    sf.set('core.new_download.slots', 3)
    sf.set('core.new_source.retries', 5)
    sf.set('core.new_source.wait', 10)
    sf.set('core.new_source.redirects', 3)
    sf.set('core.new_download.chunksize', 2097152)
    sf.set('core.new_source.timeout', 5)
    sf.set('core.new_source.user_agent',
                        'Mozilla/5.0 (X11; U; Linux i686; de; rv:1.9.2.13) ' +
                        'Gecko/20101203 Firefox/3.6.13')


    sf.save()
