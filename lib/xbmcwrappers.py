#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import xbmc
import xbmcgui

from .utils import (wrap_unicode, byteify, os_join)
from . import constants as const


def open_settings(category, action):
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % const.addonid)
    xbmc.executebuiltin('SetFocus(%i)' % (int(category) + 100 - 1))
    xbmc.executebuiltin('SetFocus(%i)' % (int(action) + 200 - 1))


class SettingsAsDict(dict):
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
        val = self.getsetting(key)
        return val

    def __setitem__(self, key, val):
        dict.__setitem__(self, key, val)
        self.setsetting(key, val)
settings = SettingsAsDict()


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
    def notification(self, heading, message, icon=os_join(const.addonpath, "resources", "notification.png"), time=None, sound=None):
        return self.dialog.notification(heading, message, icon)

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
dialogs = Dialogs()


class ScanMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.scanning = False

    def onScanStarted(self, library):
        if library == "video":
            self.scanning = True

    def onScanFinished(self, library):
        if library == "video":
            self.scanning = False

    def update_video_library(self):
        while self.scanning:
            xbmc.sleep(100)
        self.scanning = True
        xbmc.executebuiltin('UpdateLibrary(video, "", false)')
        while self.scanning:
            xbmc.sleep(100)


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
    response = xbmc.executeJSONRPC(json.dumps(req_dict))
    output = json.loads(response)
    if "error" in output:
        raise Exception("RPC error: %s,\n with message: %s" % (output, req_dict))
    result = output.get("result")
    return result


class Log(object):
    def info(self, input):
        xbmc.log(byteify("[%s] %s" % (const.addonname, input)), xbmc.LOGNOTICE)

    def debug(self, input):
        xbmc.log(byteify("[%s] %s" % (const.addonname, input)), xbmc.LOGDEBUG)
log = Log()
