import os
import sys
import xbmc
import xbmcgui
from multiprocessing.dummy import Process as Thread

from .utils import os_join
from . import constants as const
from .xbmcwrappers import log
log.info("win32 importer hack launching")

# os.environ["PATH"] += ";%s" % uni_join(const.addonpath, "lib", "win32", "pywin32_system32").decode("")
sys.path.extend([os_join(const.addonpath, "lib", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32", "lib"),
                 os_join(const.addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                 os_join(const.addonpath, "lib", "win32", "Pythonwin")])


def daemon_service():
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "true")
    log.info("win32 importer hack service running in background")
    from win32com.client import Dispatch
    import pywintypes
    import win32gui
    xbmc.Monitor().waitForAbort()


def run():
    if xbmcgui.Window(10000).getProperty("win32 importer hack running") == "true":
        log.info("win32 importer daemon already running, exiting")
        return
    daemon = Thread(target=daemon_service)
    daemon.daemon = True
    daemon.start()
