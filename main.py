#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime as dt
import sys
import os
from functools import partial
from collections import OrderedDict
import unittest
import xbmc
import xbmcgui

from lib import constants as const
from lib import library
from lib.utils import (os_join, uni_join)
from lib.xbmcwrappers import (rpc, log, dialogs)
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
    startup_debug = partial(update_mode, action="startup_debug")
    schedule_debug = partial(update_mode, action="schedule_debug")
    debugactions = {
        "refreshsettings": refresh_settings,
        "deletecookies": deletecookies,
        "test": test,
        "testsuite": testsuite,
        "open_settings": open_settings,
        "restart_service": restart_service,
        "startup_debug": startup_debug,
        "schedule_debug": schedule_debug,
    }
    debugactions[action]()


def open_settings(mode, action):
    settings = OrderedDict((
        ("setup", [
            "",
            "",
            "",
            "configureremote",
            "",
            "prioritize",
        ]),
        ("watch", [
            "browse",
            "nrk1",
            "nrk2",
            "nrk3",
            "nrksuper",
            "fantorangen",
            "barnetv",
        ]),
        ("update", [
            "watchlist",
            "update_single",
            "update_all",
            "exclude_show",
            "readd_show",
            "exclude_movie",
            "readd_movie",
            "remove_all",
        ]),
        ("startup", []),
        ("schedule", []),
        ("debug", [
            "testsuite",
            "deletecookies",
            "refreshsettings",
            "restart_service",
            "test",
            "startup_debug",
            "schedule_debug",
        ]),
    ))

    try:
        mode_loc = settings.keys().index(mode)
        action_loc = settings[mode].index(action)
    except ValueError:
        return

    xbmc.executebuiltin('Addon.OpenSettings(%s)' % const.addonid)
    xbmc.executebuiltin('SetFocus(%i)' % (mode_loc + 100))
    xbmc.executebuiltin('SetFocus(%i)' % (action_loc + 200))


def main(mode, action):
    try:
        starttime = dt.datetime.now()
        log.info("Starting %s" % const.addonname)
        if mode == "main_start":
            mode = "watch"
            action = "browse"
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
        open_settings(mode, action)


if __name__ == '__main__':
    params = get_params(sys.argv)
    mode = params['mode']
    action = params.get('action', None)
    main(mode, action)
