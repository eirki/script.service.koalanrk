import sys
import xbmc
import xbmcgui

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


def wait():
    while xbmcgui.Window(10000).getProperty("win32 importer hack running") != "true":
        xbmc.sleep(100)
    from win32com.client import Dispatch
    import pywintypes
    import win32gui


def run():
    from win32com.client import Dispatch
    import pywintypes
    import win32gui
    xbmcgui.Window(10000).setProperty("win32 importer hack running", "true")
