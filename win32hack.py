import os
import sys
import xbmc
import xbmcgui

from lib.utils import (os_join, const, log)
log.info("win32 importer hack opening")
os.environ["PATH"] += ";%s" % os_join(const.addonpath, "lib", "win32", "pywin32_system32")
sys.path.extend([os_join(const.addonpath, "lib", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32", "lib"),
                 os_join(const.addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                 os_join(const.addonpath, "lib", "win32", "Pythonwin")])
from win32com.client import Dispatch
import pywintypes
import win32gui


if __name__ == "__main__" and not xbmcgui.Window(10000).getProperty("win32 importer hack running") == "true":
    log.info("win32 importer hack running in background")
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "false")
    xbmc.Monitor().waitForAbort()
log.info("win32 importer exiting")
