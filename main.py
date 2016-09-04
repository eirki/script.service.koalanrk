#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime as dt
import sys
import os
import unittest
import xbmc
import xbmcgui

from lib import constants as const
from lib import library
from lib.utils import (os_join, uni_join)
from lib.xbmcwrappers import (rpc, log, dialogs, open_settings)
if const.os == "win":
    import pywin32setup
from lib import playback
from lib.remote import Remote


def koalasetup():
    if not os.path.exists(const.userdatafolder):
        os.makedirs(const.userdatafolder)
    if not os.path.exists(os_join(const.libpath, "%s shows" % const.provider)):
        os.makedirs(os_join(const.libpath, "%s shows" % const.provider))
    if not os.path.exists(os_join(const.libpath, "%s movies" % const.provider)):
        os.makedirs(os_join(const.libpath, "%s movies" % const.provider))


def is_libpath_added():
    sources = rpc("Files.GetSources", media="video")
    for source in sources.get('sources', []):
        if source['file'].startswith(uni_join(const.libpath, const.provider)):
            return True
    return False


def refresh_settings():
    xbmc.executebuiltin('Dialog.Close(dialog)')
    xbmc.executebuiltin('ReloadSkin')
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % const.addonid)


def restart_service():
    rpc("Addons.SetAddonEnabled", addonid=const.addonid, enabled=False)
    rpc("Addons.SetAddonEnabled", addonid=const.addonid, enabled=True)


def deletecookies():
    cookiefile = os_join(const.userdatafolder, "cookies")
    if os.path.isfile(cookiefile):
        os.remove(cookiefile)


def testsuite():
    suite = unittest.TestLoader().discover(start_dir='tests')
    unittest.TextTestRunner().run(suite)


def test():
    pass


def get_params(argv):
    params = {}
    if argv in (["main.py"], ['']):
        # if addon-icon clicked or addon selected in program addons list
        params = {"mode": "main_start"}
    else:
        # if action triggered from settings/service
        arg_pairs = argv[1:]
        for arg_pair in arg_pairs:
            arg, val = arg_pair.split('=')
            params[arg] = val
    if not params:
        raise Exception("Unknown sys argv: %s" % argv)
    return params


def setup_mode(action):
    if action == "configureremote":
        remote = Remote()
        remote.configure()
    elif action == "prioritize":
        library.main(action="prioritize")


def watch_mode(action):
    playback.live(action)


def update_mode(action):
    if xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true":
        if action in ["startup", "schedule"]:
            return
        run = dialogs.yesno(heading="Running", line1="Koala is running. ",
                            line2="Running multiple instances cause instablity.", line3="Continue?")
        if not run:
            return
    koalasetup()
    if not is_libpath_added():
        dialogs.ok(heading="Koala path not in video sources",
                   line1="Koala library paths have not been added to Kodi video sources:",
                   line2=uni_join(const.libpath, "%s shows" % const.provider),
                   line3=uni_join(const.libpath, "%s movies" % const.provider))
        return
    try:
        xbmcgui.Window(10000).setProperty("%s running" % const.addonname, "true")
        library.main(action)
    finally:
        xbmcgui.Window(10000).setProperty("%s running" % const.addonname, "false")


def debug_mode(action):
    debugactions = {
        "refreshsettings": refresh_settings,
        "deletecookies": deletecookies,
        "test": test,
        "testsuite": testsuite,
        "restart_service": restart_service,
    }
    debugactions[action]()


def main(argv=None):
    if argv is None:
        argv = get_params(sys.argv)
    mode = argv['mode']
    action = argv.get('action', None)
    settings_coord = argv['reopen_settings'].split() if 'reopen_settings' in argv else None

    try:
        starttime = dt.datetime.now()
        log.info("Starting %s" % const.addonname)
        if mode == "main_start":
            open_settings(category=2, action=1)
            return
        modes = {
            "setup": setup_mode,
            "update": update_mode,
            "watch": watch_mode,
            "debug": debug_mode,
        }
        selected_mode = modes[mode]
        selected_mode(action)
    finally:
        log.info("%s finished (in %s)" % (const.addonname, str(dt.datetime.now() - starttime)))
        if settings_coord:
            open_settings(*settings_coord)


if __name__ == '__main__':
    main()
