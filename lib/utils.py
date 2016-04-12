#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from functools import wraps
import os
import sys
import xbmc
import xbmcgui

from . import constants as const


def byteify(input):
    if isinstance(input, dict):
        return dict((byteify(key), byteify(value)) for key, value in input.iteritems())
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, tuple):
        return [byteify(element) for element in list(input)]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input


def debyteify(input):
    if isinstance(input, dict):
        return dict((debyteify(key), debyteify(value)) for key, value in input.iteritems())
    elif isinstance(input, list):
        return [debyteify(element) for element in input]
    elif isinstance(input, tuple):
        return [debyteify(element) for element in list(input)]
    elif isinstance(input, str):
        return input.decode('utf-8')
    else:
        return input


def stringtofile(string):
    string = string.replace('<', '')
    string = string.replace('>', '')
    string = string.replace(':', '')
    string = string.replace('"', '')
    string = string.replace('/', '')
    string = string.replace('\\', '')
    string = string.replace('|', '')
    string = string.replace('?', '')
    string = string.replace('*', '')
    string = string.replace('...', '')
    string = string[:90]
    return string


def wrap_unicode(func):
    '''encodes input from unicode to utf-8, and decodes output from utf-8 to unicode'''
    @wraps(func)
    def wrapper(*args, **kwargs):
        utf_args, utf_kwargs = byteify((args, kwargs))
        output = func(*utf_args, **utf_kwargs)
        unic_output = debyteify(output)
        return unic_output
    return wrapper


def os_join(*args):
    path = os.path.join(*args)
    if const.os == "win":
        return path
    else:
        return path.encode("utf-8")

uni_join = os.path.join


def win32hack():
    xbmc.executebuiltin("RunScript(%s, %s)" % (os_join(const.addonpath, "win32hack.py"), uni_join(const.addonpath, "lib", "win32")))
    while xbmcgui.Window(10000).getProperty("win32 importer hack running") != "true":
        xbmc.sleep(100)
    sys.path.extend([os_join(const.addonpath, "lib", "win32"),
                     os_join(const.addonpath, "lib", "win32", "win32"),
                     os_join(const.addonpath, "lib", "win32", "win32", "lib"),
                     os_join(const.addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                     os_join(const.addonpath, "lib", "win32", "Pythonwin")])
