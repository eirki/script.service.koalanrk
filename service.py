#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import datetime as dt
import xbmc
import xbmcgui
from threading import Thread

from lib import constants as const
from lib import kodi
if const.os == "win":
    import pywin32setup
from lib import playback


def minutes_to_next_rounded_update_time():
    frequency_secs = {
        "15 min": 900,
        "30 min": 1800,
        "1 hour": 3600,
        "2 hours": 7200
    }[kodi.settings["schedule frequency"]]
    frequency = dt.timedelta(seconds=frequency_secs)
    now = dt.datetime.now()
    time_since_hour = dt.timedelta(minutes=now.minute, seconds=now.second)
    scheduled_next_unrounded = frequency + time_since_hour
    scheduled_next = (scheduled_next_unrounded.seconds // frequency_secs) * frequency_secs
    till_scheduled_next = scheduled_next - time_since_hour.seconds
    return till_scheduled_next


def run_schedule():
    timeout = minutes_to_next_rounded_update_time()
    kodi.log("Starting update scheduler, next update at %s" %
             (dt.datetime.now() + dt.timedelta(seconds=timeout)).strftime("%H:%M"))
    while True:
        abort = xbmc.Monitor().waitForAbort(timeout)
        if abort:
            kodi.log("Closing background service")
            break
        timeout = {
            "15 min": 900,
            "30 min": 1800,
            "1 hour": 3600,
            "2 hours": 7200
        }[kodi.settings["schedule frequency"]]

        scheduler_enabled = kodi.settings["enable schedule"]
        player_active = kodi.rpc("Player.GetActivePlayers")
        koala_active = xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true"
        if player_active or koala_active or not scheduler_enabled:
            continue

        kodi.log("Starting scheduled update next update at %s" %
                 (dt.datetime.now() + dt.timedelta(seconds=timeout)).strftime("%H:%M"))
        xbmc.executebuiltin("RunScript(%s, mode=library, action=schedule)" % const.addonid)


if __name__ == '__main__':
    Thread(target=playback.PlaybackManager).start()

    if kodi.settings["enable startup"]:
        xbmc.executebuiltin("RunScript(%s, mode=library, action=startup)" % const.addonid)
    run_schedule()
