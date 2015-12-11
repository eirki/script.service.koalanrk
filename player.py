#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import arrow
from collections import defaultdict
try:
    import simplejson as json
except ImportError:
    import json
import os
from os.path import exists
import re
import shutil
import sqlite3
import subprocess
import xbmc
from datetime import timedelta

from libraries.utils import settings
from libraries.utils import log
from libraries.utils import mkpath
from libraries.utils import kodiRPC
from libraries.utils import const


def getplayingvideofile():
    if xbmc.Player().isPlayingAudio():
        log.info("Audio file playing")
        playingfile = kodiRPC("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=0)
    if xbmc.Player().isPlayingVideo():
        log.info("Video file playing")
        playingfile = kodiRPC("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=1)
    log.info("Playing: %s" % playingfile["item"])
    if "item" in playingfile:
        playingfile = playingfile["item"]
    return playingfile


def gen_epdict(playingfile):
    playingepcode = 'S%02dE%02d' % (playingfile['season'], playingfile['episode'])
    log.debug(playingepcode)
    tvshowid = playingfile["tvshowid"]
    tvshow_dict = kodiRPC("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
                          "playcount", "season", "episode", "file", "runtime"])
    epdict = {}
    for episode in tvshow_dict['episodes']:
        epcode = 'S%02dE%02d' % (episode['season'], episode['episode'])
        if epcode >= playingepcode:
            kodiid = episode['episodeid']
            playcount = episode['playcount']
            runtime = episode['runtime']
            with open(episode['file'], 'r') as txt:
                nrkid = re.sub(r'.*http://tv.nrk.no/(.*?)".*', r"\1", txt.read())
            epdict[nrkid] = [epcode, kodiid, playcount, runtime]
    return epdict


def timestamp_to_win32(timestamp):
    """Convert timestamp to win32 timestamp (microseconds since 01.01.1601)
    Windows NT time (used by chrome) is specified as the number of 100 nanosecond intervals since January 1, 1601.
    UNIX time (used by arrow) is specified as the number of seconds since January 1, 1970.
    There are 134,774 days (or 11,644,473,600 seconds) between these dates."""

    # Conversion between a Jan 1 1601 epoch and a Jan 1 1970 epoch is 134774 days.
    starttime32 = timestamp.replace(days=+134774)
    # Conversion between seconds and microseconds is 1000000
    starttime_micsec = long(starttime32.timestamp * 1000000)
    return starttime_micsec


def win32_to_timestamp(win32):
    # add number of microseconds to 01.01.1601 epoch
    timestamp = arrow.get(1601, 1, 1).replace(microseconds=+win32)
    return timestamp


def get_chrome_urls(starttime):
    usr = os.path.expanduser("~")
    shutil.copy(mkpath(usr, "AppData/Local/Google/Chrome/User Data/Default/History"),
                mkpath(const.userdatafolder, "chromehistory"))
    starttimewin32 = timestamp_to_win32(starttime)
    with sqlite3.connect(mkpath(const.userdatafolder, "chromehistory")) as con:
        cursor = con.cursor()
        cursor.execute("SELECT last_visit_time, url FROM urls WHERE last_visit_time>'%s'" % starttimewin32)
        visited_urls = [[win32_to_timestamp(time), url] for time, url in cursor.fetchall()]
    visited_urls.sort(reverse=True)
    ntflxlist = get_nrk_watched(visited_urls)
    return ntflxlist


def get_ie_urls(historyfile):
    visited_urls = []
    with open(historyfile) as txt:
        for line in txt.readlines():
            time, url = line.strip().split()
            visit_time = arrow.get(time, "YYYYMMDDHHmmss")
            visited_urls.append([visit_time, url])
    visited_urls.sort(reverse=True)
    ntflxlist = get_nrk_watched(visited_urls)
    return ntflxlist


def get_nrk_watched(visited_urls):
    watched_nrk = []
    for i, (start, url) in enumerate(visited_urls):
        log.info("Watched url: %s" % url)
        nrkid, found = re.subn(r'.*//tv.nrk.no/(.*).*', r"\1", url)
        if found:
            log.info("Extracted nrkid: %s" % nrkid)
            end = visited_urls[i-1][0] if watched_nrk else arrow.utcnow()
            duration = end - start
            watched_nrk.append([duration, nrkid])
            log.info("Duration: %s" % duration.seconds)
    watched_nrk.reverse()
    return watched_nrk


def mark_watched(epdict, watched):
    for watchedduration, nrkid in watched:
        if nrkid in epdict:
            epcode, kodiid, playcount, runtime = epdict[nrkid]
            runtime = timedelta(seconds=runtime)
            log.info("%s runtime: %s" % (epcode, runtime.seconds))
            if watchedduration.seconds / runtime.seconds >= 0.9:
                addplaycount(kodiid, playcount)
                log.info("%s: Marked as watched" % epcode)
            else:
                log.info("%s: Skipped, only partially watched" % epcode)
            #     add partially watched flag?


def addplaycount(kodiid, playcount):
    playcount += 1
    now = arrow.now().format("%d-%m-%Y %H:%M:%S")
    kodiRPC("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


def getremotemapping():
    try:
        with open(mkpath(const.userdatafolder, "remotemapping.json")) as j:
            remotemapping = defaultdict(str, json.load(j))
    except IOError:
        remotemapping = defaultdict(str)
    controls = [remotemapping["Play"], remotemapping["Pause"], remotemapping["Stop"],
                remotemapping["Forward"], remotemapping["Rewind"]]
    return controls


class ViewingSession():
    def __init__(self, playingfile):
        log.info("playbackstart starting")
        self.playingfile = playingfile
        self.starttime = arrow.now()
        self.remoteprocess = None
        if settings["starter"]:
            log.info("Launching starter utility")
            subprocess.Popen([const.ahkexe, mkpath(const.ahkfolder, "starter.ahk"), settings["browser"]])
        if settings["remote"]:
            mapping = getremotemapping()
            log.info("Launching remote utility")
            self.remoteprocess = subprocess.Popen([const.ahkexe, mkpath(const.ahkfolder, "remote.ahk"), settings["browser"]]+mapping)
        if settings["mark auto-played"] and playingfile["file"].startswith(mkpath(const.libpath, "NRK shows")):
            if settings["browser"] == "Internet Explorer":
                self.historyfile = mkpath(const.userdatafolder, "iehistory %s" % self.starttime.timestamp)
                log.info("Launching IE historyfile utility")
                self.ieprocess = subprocess.Popen(
                    [mkpath(const.ahkfolder, "AutoHotkey.exe"), mkpath(const.ahkfolder, "save iehistory.ahk"), self.historyfile])
            self.epdict = gen_epdict(self.playingfile)
            log.info(self.epdict)
        log.info("playbackstart finished")

    def ended(self):
        log.info("playbackend starting")
        if self.remoteprocess:
            self.remoteprocess.terminate()
        if settings["mark auto-played"]:
            if settings["browser"] == "Internet Explorer":
                log.info("Closing IE historyfile utility")
                self.ieprocess.terminate()
                self.watched = get_ie_urls(self.historyfile)
                if exists(self.historyfile):
                    os.remove(self.historyfile)
            elif settings["browser"] == "Chrome":
                self.watched = get_chrome_urls(self.starttime)
            mark_watched(self.epdict, self.watched)
        log.info("playbackend finished")


class MyPlayer(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)
        self.session = None

    def onPlayBackStarted(self):
        playingfile = getplayingvideofile()
        if playingfile["file"].startswith(mkpath(const.libpath, "NRK")):
            self.session = ViewingSession(playingfile)

    def onPlayBackEnded(self):
        if self.session:
            self.session.ended()
            self.session = None


if const.os == "windows" and (settings["mark auto-played"] or settings["remote"]):
    player = MyPlayer()
    xbmc.Monitor().waitForAbort()
