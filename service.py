#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
print 12345

import datetime as dt
import xbmc
import xbmcgui

from lib import constants as const
from lib.xbmcwrappers import (settings, rpc, log)
if const.os == "win":
    from lib import win32hack
    win32hack.run_importer_daemon()
from lib import playback


def minutes_to_next_rounded_update_time():
    frequency_secs = [15, 30, 60, 120][settings["schedule frequency"]] * 60
    frequency = dt.timedelta(seconds=frequency_secs)
    now = dt.datetime.now()
    time_since_hour = dt.timedelta(minutes=now.minute, seconds=now.second)
    scheduled_next_unrounded = frequency + time_since_hour
    scheduled_next = (scheduled_next_unrounded.seconds // frequency_secs) * frequency_secs
    till_scheduled_next = scheduled_next - time_since_hour.seconds
    return till_scheduled_next


def run_schedule():
    timeout = minutes_to_next_rounded_update_time()
    log.info("Starting update scheduler, next update at %s" %
             (dt.datetime.now() + dt.timedelta(seconds=timeout)).strftime("%H:%M"))
    while True:
        abort = xbmc.Monitor().waitForAbort(timeout)
        if abort:
            log.info("Closing background service")
            break
        timeout = [15, 30, 60, 120][settings["schedule frequency"]] * 60

        scheduler_enabled = settings["enable schedule"]
        player_active = rpc("Player.GetActivePlayers")
        koala_active = xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true"
        if player_active or koala_active or not scheduler_enabled:
            continue

        log.info("Starting scheduled update next update at %s" %
                 (dt.datetime.now() + dt.timedelta(seconds=timeout)).strftime("%H:%M"))
        xbmc.executebuiltin("RunScript(script.service.koalanrk, mode=library, action=schedule)")


if __name__ == '__main__':
    playback.Monitor()
    if settings["enable startup"]:
        xbmc.executebuiltin("RunScript(script.service.koalanrk, mode=library, action=startup)")
    run_schedule()
