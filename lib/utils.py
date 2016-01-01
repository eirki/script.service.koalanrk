#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from functools import wraps
import json
import os
import sys
import xbmc
import xbmcaddon
import xbmcgui


class Constants(object):
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.addonpath = xbmc.translatePath(self.addon.getAddonInfo('path')).decode("utf-8")
        self.userdatafolder = xbmc.translatePath("special://profile/addon_data/script.service.koalanrk").decode("utf-8")
        if self.addon.getSetting("usecustomLibPath"):
            self.libpath = xbmc.translatePath(self.addon.getSetting("LibPath")).decode("utf-8")
        else:
            self.libpath = xbmc.translatePath("special://profile/addon_data/script.service.koalanrk/Library").decode("utf-8")
        self.ahkfolder = os.path.join(self.addonpath, "resources", "autohotkey")
        self.ahkexe = os.path.join(self.ahkfolder, "AutoHotkey.exe")

        if xbmc.getCondVisibility("system.platform.linux"):
            self.os = "linux"
        elif xbmc.getCondVisibility("system.platform.windows"):
            self.os = "windows"
        elif xbmc.getCondVisibility("system.platform.osx"):
            self.os = "osx"
        elif xbmc.getCondVisibility("system.platform.android"):
            self.os = "android"
        else:
            self.os = "other"

    def __setattr__(self, name, value):
        if name in self.__dict__:
            raise Exception("Can't rebind constant")
        self.__dict__[name] = value
const = Constants()


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


def wrap_unicode(func):
    '''encodes input from unicode to utf-8, and decodes output from utf-8 to unicode'''
    @wraps(func)
    def wrapper(*args, **kwargs):
        utf_args, utf_kwargs = byteify((args, kwargs))
        output = func(*utf_args, **utf_kwargs)
        unic_output = debyteify(output)
        return unic_output
    return wrapper


def mkpath(*args):
    path = os.path.join(*args)
    if const.os == "windows":
        return path
    else:
        return path.encode("utf-8")


class SettingsDict(dict):
    @wrap_unicode
    def getsetting(self, key):
        val = const.addon.getSetting(key)
        if val in ["true", "false"]:
            val = val == "true"
        elif val.isdigit():
            val = int(val)
        return val

    @wrap_unicode
    def setsetting(self, key, val):
        if isinstance(val, (bool, int)):
            val = str(val).lower()
        const.addon.setSetting(key, val)

    def __getitem__(self, key):
        if key in self:
            val = dict.__getitem__(self, key)
        else:
            val = self.getsetting(key)
        dict.__setitem__(self, key, val)
        return val

    def __setitem__(self, key, val):
        dict.__setitem__(self, key, val)
        self.setsetting(key, val)
settings = SettingsDict()


class Dialogs(object):
    def __init__(self):
        self.dialog = xbmcgui.Dialog()

    @wrap_unicode
    def browse(self, type, heading, shares, mask=None, useThumbs=None,
               treatAsFolder=None, default=None, enableMultiple=None):
        return self.dialog.browse(type, heading, shares, mask, useThumbs,
                                  treatAsFolder, default, enableMultiple)

    @wrap_unicode
    def input(self, heading, default=None, type=None, option=None, autoclose=None):
        return self.dialog.input(heading, default, type, option, autoclose)

    @wrap_unicode
    def notification(self, heading, message, icon=None, time=None, sound=None):
        return self.dialog.notification(heading, message, icon, time, sound)

    @wrap_unicode
    def numeric(self, type, heading, default=None):
        return self.dialog.numeric(type, heading, default)

    @wrap_unicode
    def ok(self, heading, line1, line2=None, line3=None):
        return self.dialog.ok(heading, line1, line2, line3)

    @wrap_unicode
    def select(self, heading, list):
        return self.dialog.select(heading, list)

    @wrap_unicode
    def yesno(self, heading, line1, line2=None, line3=None):
        return self.dialog.yesno(heading, line1, line2, line3)


class PDialog(object):
    if settings["startupnotification"] or sys.argv == ['']:
        def __init__(self):
            self.active = False

        def create(self, heading, message=None, force=False):
            self.active = True
            self.force = force
            self.perc = 1
            self.pDialog = xbmcgui.DialogProgressBG()
            self.pDialog.create(heading, message)

        def update(self, percent=None, heading=None, message=None, increment=False):
            self.perc = percent
            self.pDialog.update(percent, message=message)

        def close(self):
            while self.perc < 100:
                self.perc += 2
                self.pDialog.update(self.perc)
                xbmc.sleep(10)
            self.pDialog.close()

    else:
        def __init__(self):
            pass

        def create(self, heading, message=None, force=False):
            pass

        def update(self, percent=None, heading=None, message=None, increment=False):
            pass

        def close(self):
            pass


class ScanMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.scanning = False

    def onScanStarted(self, database):
        self.scanning = True

    def onScanFinished(self, database):
        self.scanning = False

    def update_video_library(self):
        while self.scanning:
            xbmc.sleep(100)
        log.debug("Updating video library")
        self.scanning = True
        xbmc.executebuiltin('UpdateLibrary(video, "", false)')
        while self.scanning:
            xbmc.sleep(100)
        log.debug("Library update complete")


def rpc(method, multifilter=False, **kwargs):
    if multifilter:
        conditional = multifilter.keys()[0]
        rules = multifilter.values()[0]
        filterkwarg = {conditional: [{"field": f, "operator": o, "value": v} for f, o, v in rules]}
        kwargs.update({"filter": filterkwarg})
    if kwargs:
        req_dict = {"jsonrpc": "2.0", "id": "1", "method": method, "params": kwargs}
    else:
        req_dict = {"jsonrpc": "2.0", "id": "1", "method": method}
    log.debug(req_dict)
    response = xbmc.executeJSONRPC(json.dumps(req_dict))
    d = json.loads(response)
    output = d.get("result")
    return output


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
    if const.os == "windows":
        return string
    else:
        return string.encode("utf-8")


class Log(object):
    def info(self, input):
        xbmc.log(byteify("[Koala NRK] %s" % input), xbmc.LOGNOTICE)

    def debug(self, input):
        xbmc.log(byteify("[Koala NRK] %s" % input), xbmc.LOGDEBUG)


monitor = ScanMonitor()
progress = PDialog()
dialogs = Dialogs()
log = Log()
