import os
import sys
import time

print "starting wierd importer"
os.environ["PATH"] += ";%s" % "C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32\\pywin32_system32"
sys.path.extend(["C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32",
                 "C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32\\win32",
                 "C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32\\win32\\lib",
                 "C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32\\pypiwin32-219.data\\scripts",
                 "C:\\Programmer\\Kodi\\portable_data\\addons\\script.service.koalanrk\\lib\\win32\\Pythonwin"])
from win32com.client import Dispatch
import pywintypes
import win32gui
while True:
    time.sleep(1000000)
