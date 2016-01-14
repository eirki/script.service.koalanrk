# Magic utility that "redirects" to pywintypesxx.dll
import imp, sys, os
def __import_pywin32_system_module__(modname, globs):
    # This has been through a number of iterations.  The problem: how to
    # locate pywintypesXX.dll when it may be in a number of places, and how
    # to avoid ever loading it twice.  This problem is compounded by the
    # fact that the "right" way to do this requires win32api, but this
    # itself requires pywintypesXX.
    # And the killer problem is that someone may have done 'import win32api'
    # before this code is called.  In that case Windows will have already
    # loaded pywintypesXX as part of loading win32api - but by the time
    # we get here, we may locate a different one.  This appears to work, but
    # then starts raising bizarre TypeErrors complaining that something
    # is not a pywintypes type when it clearly is!

    # So in what we hope is the last major iteration of this, we now
    # rely on a _win32sysloader module, implemented in C but not relying
    # on pywintypesXX.dll.  It then can check if the DLL we are looking for
    # lib is already loaded.

    filename = "%s27.dll" % modname
    # py2k and py3k differences:
    # On py2k, after doing "imp.load_module('pywintypes')", sys.modules
    # is unchanged - ie, sys.modules['pywintypes'] still refers to *this*
    # .py module - but the module's __dict__ has *already* need updated
    # with the new module's contents.
    # However, on py3k, sys.modules *is* changed - sys.modules['pywintypes']
    # will be changed to the new module object.
    # SO: * on py2k don't need to update any globals.
    #     * on py3k we update our module dict with the new module's dict and
    #       copy its globals to ours.
    import _win32sysloader
    _win32sysloader.LoadModule(filename)
    # old_mod = sys.modules[modname]
    # Python can load the module
    found = r"C:\Programmer\Kodi\portable_data\addons\script.service.koalanrk\lib\win32\pywin32_system32\%s27.dll" % modname
    imp.load_dynamic(modname, found)
    # Check the sys.modules[] behaviour we describe above is true...
    # if sys.version_info < (3,0):
    #     assert sys.modules[modname] is old_mod
    #     assert mod is old_mod
    # else:
    #     assert sys.modules[modname] is not old_mod
    #     assert sys.modules[modname] is mod
    #     # as above - re-reset to the *old* module object then update globs.
    #     sys.modules[modname] = old_mod
    #     globs.update(mod.__dict__)


__import_pywin32_system_module__("pywintypes", globals())
