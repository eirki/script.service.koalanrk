#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import xbmc
import xbmcgui

from . import constants as const
from . import utils


def open_settings(category, action):
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % const.addonid)
    xbmc.executebuiltin('SetFocus(%i)' % (int(category) + 100 - 1))
    xbmc.executebuiltin('SetFocus(%i)' % (int(action) + 200 - 1))


class SettingsAsDict(dict):
    @utils.wrap_unicode
    def getsetting(self, key):
        val = const.addon.getSetting(key)
        if val in ["true", "false"]:
            val = val == "true"
        elif val.isdigit():
            val = int(val)
        return val

    @utils.wrap_unicode
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


class Dialog(object):
    def __init__(self):
        self.dialog = xbmcgui.Dialog()

    @classmethod
    @utils.wrap_unicode
    def browse(cls, *args, **kwargs):
        return cls().dialog.browse(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def input(cls, *args, **kwargs):
        return cls().dialog.input(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def notification(cls, *args, **kwargs):
        kwargs["icon"] = utils.os_join(const.addonpath, "resources", "notification.png")
        return cls().dialog.notification(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def numeric(cls, *args, **kwargs):
        return cls().dialog.numeric(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def ok(cls, *args, **kwargs):
        return cls().dialog.ok(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def select(cls, *args, **kwargs):
        return cls().dialog.select(*args, **kwargs)

    @classmethod
    @utils.wrap_unicode
    def yesno(cls, *args, **kwargs):
        return cls().dialog.yesno(*args, **kwargs)


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


def log(input, debug=False):
    xbmc.log(utils.byteify("[%s] %s" % (const.addonname, input)), level=xbmc.LOGNOTICE if debug is False else xbmc.LOGDEBUG)
