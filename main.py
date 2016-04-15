#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime
import sys
import os
import unittest
import xbmc
import xbmcgui

from lib import constants as const
from lib import library
from lib.utils import (os_join, uni_join, win32hack)
from lib.xbmcwrappers import (settings, rpc, log, dialogs, open_settings)
if const.os == "win":
    win32hack()
import playback
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


def restart_playback_service():
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
    print const.addonid


def get_params(argv):
    if argv == ['']:
        params = {"mode": "library", "action": "startup"}
    elif argv == ["main.py"]:
        params = {"mode": "setting", "action": "open_settings"}
    else:
        params = {}
        if argv[0] == "main.py":
            arg_pairs = argv[1:]
        elif argv[0] == "plugin://%s/" % const.addonid:
            arg_pairs = argv[2][1:].split("&")
        for arg_pair in arg_pairs:
            arg, val = arg_pair.split('=')
            params[arg] = val
    return params


def setting_mode(action):
    if action == "configureremote":
        remote = Remote()
        remote.configure()
    else:
        settingsactions = {
            "refreshsettings": refresh_settings,
            "deletecookies": deletecookies,
            "test": test,
            "testsuite": testsuite,
            "open_settings": open_settings,
            "restart_playback_service": restart_playback_service
        }
        settingsactions[action]()


def play_mode(action):
    playback.live(action)


def library_mode(action):
    if action == "startup" and not (settings["watchlist on startup"] or settings["shows on startup"] or
                                    settings["prioritized on startup"]):
        return
    if xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true":
        if action == "startup":
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


def main(mode, action):
    try:
        starttime = datetime.now()
        log.info("Starting %s" % const.addonname)
        modes = {
            "setting": setting_mode,
            "play": play_mode,
            "library": library_mode,
        }
        selected_mode = modes[mode]
        selected_mode(action)
    finally:
        log.info("%s finished (in %s)" % (const.addonname, str(datetime.now() - starttime)))
        settings_order = {
            "watchlist":       [2, 1],
            "update_single":   [2, 2],
            "update_all":      [2, 3],
            "exclude_show":    [2, 4],
            "readd_show":      [2, 5],
            "exclude_movie":   [2, 6],
            "readd_movie":     [2, 7],
            "prioritize":      [3, 4],
            "configureremote": [4, 8],
            "testsuite":       [5, 1],
            "remove_all":      [5, 2],
            "deletecookies":   [5, 3],
            "refreshsettings": [5, 4],
            "restart_playback_service": [5, 5],
            "test":            [5, 6],
            "startup_debug":   [5, 7],
            }
        settinglocation = settings_order.get(action)
        if settinglocation:
            open_settings(*settinglocation)


if __name__ == '__main__':
        params = get_params(sys.argv)
        mode = params.get('mode', None)
        action = params.get('action', None)
        main(mode, action)
