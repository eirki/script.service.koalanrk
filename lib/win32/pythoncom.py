# Magic utility that "redirects" to pythoncomxx.dll
# import pywintypes
# pywintypes.__import_pywin32_system_module__("pythoncom", globals())
import _win32sysloader
import imp
_win32sysloader.LoadModule("pythoncom27.dll")
imp.load_dynamic("pythoncom", r"C:\Programmer\Kodi\portable_data\addons\script.service.koalanrk\lib\win32\pywin32_system32\pythoncom27.dll")
