#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import os
import xbmc
import xbmcgui
if __name__ != "__main__":
    from . import constants as const
    from .utils import uni_join
    addonpath = const.addonpath
else:
    addonpath = sys.argv[-1]


def join(*args):
    path = os.path.join(*args)
    return path.encode(sys.getfilesystemencoding())


def add_to_syspath():
    sys.path.extend([join(addonpath, "lib", "win32"),
                     join(addonpath, "lib", "win32", "win32"),
                     join(addonpath, "lib", "win32", "win32", "lib"),
                     join(addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                     join(addonpath, "lib", "win32", "Pythonwin")])


def run_importer_daemon():
    if xbmcgui.Window(10000).getProperty("win32 importer hack running") in ["true", "launching"]:
        return
    xbmc.executebuiltin("RunScript(%s, %s)".encode("utf-8") % (uni_join(addonpath, "lib", "win32hack.py"), addonpath))
    while xbmcgui.Window(10000).getProperty("win32 importer hack running") != "true":
        xbmc.sleep(100)



def importer():
    if xbmcgui.Window(10000).getProperty("win32 importer hack running") in ["true", "launching"]:
        return
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "launching")
    xbmc.log("launching daemon service from %s" % addonpath)
    from win32com.client import Dispatch
    import pywintypes
    import win32gui
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "true")
    while not xbmc.abortRequested:
        xbmc.sleep(500)
    xbmc.log("closing daemon service")


if __name__ == "__main__":
    add_to_syspath()
    importer()
