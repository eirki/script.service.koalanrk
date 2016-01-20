import os
import sys
import time
import xbmc

from lib.utils import (os_join, const)

os.environ["PATH"] += ";%s" % os_join(const.addonpath, "lib", "win32", "pywin32_system32")
sys.path.extend([os_join(const.addonpath, "lib", "pyHook"),
                 os_join(const.addonpath, "lib", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32"),
                 os_join(const.addonpath, "lib", "win32", "win32", "lib"),
                 os_join(const.addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                 os_join(const.addonpath, "lib", "win32", "Pythonwin")])
from win32com.client import Dispatch
import pywintypes
import win32gui

if __name__ == "__main__":
    xbmc.Monitor().waitForAbort()
