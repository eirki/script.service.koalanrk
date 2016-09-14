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


def start():
    open_settings(category=2, action=1)


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


def run_testsuite():
    suite = unittest.TestLoader().discover(start_dir='tests')
    unittest.TextTestRunner().run(suite)


def configure_remote():
    remote = Remote()
    remote.configure()


def test():
    pass


def get_params(argv):
    params = {}
    if argv in (["main.py"], ['']):
        # if addon-icon clicked or addon selected in program addons list
        params = {"mode": "main", "action": "start"}
    else:
        # if action triggered from settings/service
        arg_pairs = argv[1:]
        for arg_pair in arg_pairs:
            arg, val = arg_pair.split('=')
            params[arg] = val
    if not params:
        raise Exception("Unknown sys argv: %s" % argv)
    return params


def watch_mode(action):
    playback.live(action)


def library_mode(action):
    if xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true":
        if action in ["startup", "schedule"]:
            return
        run = dialogs.yesno(heading="Running", line1="Koala is running. ",
                            line2="Running multiple instances may cause instablity.", line3="Continue?")
        if not run:
            return
    koalasetup()
    if not is_libpath_added():
        dialogs.ok(heading="Koala path not in video sources",
                   line1="Koala library paths have not been added to Kodi video sources:",
                   line2=uni_join(const.libpath, "%s shows" % const.provider),
                   line3=uni_join(const.libpath, "%s movies" % const.provider))
        return

    starttime = dt.datetime.now()
    log.info("Starting %s" % action)
    xbmcgui.Window(10000).setProperty("%s running" % const.addonname, "true")
    try:
        library.main(action)
    finally:
        xbmcgui.Window(10000).setProperty("%s running" % const.addonname, "false")
        log.info("Finished %s in %s" % (action, str(dt.datetime.now() - starttime)))


def main_mode(action):
    switch = {
        "start": start,
        "configure_remote": configure_remote,
        "refresh_settings": refresh_settings,
        "test": test,
        "run_testsuite": run_testsuite,
    }
    switch[action]()


def main(argv=None):
    if argv is None:
        argv = get_params(sys.argv)
    mode = argv['mode']
    action = argv.get('action', None)
    settings_coord = argv.get('reopen_settings', "").split()

    switch = {
        "main": main_mode,
        "library": library_mode,
        "watch": watch_mode,
    }
    selected_mode = switch[mode]
    try:
        selected_mode(action)
    finally:
        if settings_coord:
            open_settings(*settings_coord)


if __name__ == '__main__':
    main()
