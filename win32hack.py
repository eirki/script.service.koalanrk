#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import os
import xbmc
import xbmcgui


def main():
    if xbmcgui.Window(10000).getProperty("win32 importer hack running") == "true":
        return
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "true")
    xbmc.log("launching daemon service")
    win32path = sys.argv[-1]
    sys.path.extend([os.path.join(win32path),
                     os.path.join(win32path, "win32"),
                     os.path.join(win32path, "win32", "lib"),
                     os.path.join(win32path, "pypiwin32-219.data", "scripts"),
                     os.path.join(win32path, "Pythonwin")])

    from win32com.client import Dispatch
    import pywintypes
    import win32gui
    # xbmc.Monitor().waitForAbort()
    while not xbmc.abortRequested:
        xbmc.sleep(500)
    xbmc.log("closing daemon service")


if __name__ == "__main__":
    main()
