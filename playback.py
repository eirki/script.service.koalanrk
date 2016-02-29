#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import re
from datetime import (timedelta, datetime)
import sys
from collections import namedtuple
import multiprocessing.dummy as threading
import xbmc

from chromote import Chromote

from lib import constants as const
from lib.utils import (os_join, uni_join)
from lib.xbmcwrappers import (log, settings, rpc)
if const.os == "win":
    sys.path.extend([os_join(const.addonpath, "lib", "win32"),
                     os_join(const.addonpath, "lib", "win32", "win32"),
                     os_join(const.addonpath, "lib", "win32", "win32", "lib"),
                     os_join(const.addonpath, "lib", "win32", "pypiwin32-219.data", "scripts"),
                     os_join(const.addonpath, "lib", "win32", "Pythonwin")])
    from win32com.client import Dispatch
    import pywintypes
    import win32gui

from lib.remote import Remote


def getplayingvideofile():
    if xbmc.Player().isPlayingAudio():
        log.info("Audio file playing")
        playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=0)
    if xbmc.Player().isPlayingVideo():
        log.info("Video file playing")
        playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=1)
    log.info("Playing: %s" % playingfile["item"])
    if "item" in playingfile:
        playingfile = playingfile["item"]
    return playingfile


def get_stored_episodes(kodiid):
    Epinfo = namedtuple("Epinfo", "code kodiid playcount runtime")
    playingfile = rpc("VideoLibrary.GetEpisodeDetails", episodeid=int(kodiid), properties=["tvshowid", "season", "episode"])
    tvshowid = playingfile["episodedetails"]["tvshowid"]
    tvshow_dict = rpc("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
                      "playcount", "season", "episode", "file", "runtime"])
    epdict = {}
    for episode in tvshow_dict['episodes']:
        epcode = 'S%02dE%02d' % (episode['season'], episode['episode'])
        kodiid = episode['episodeid']
        playcount = episode['playcount']
        runtime = timedelta(seconds=episode['runtime'])
        with open(episode['file'], 'r') as txt:
            urlid = re.sub(r"urlid=([^&]*)", r"\1", txt.read())
        epdict[urlid] = Epinfo(epcode, kodiid, playcount, runtime)
    log.info(epdict)
    return epdict


def setplaycount(kodiid, playcount):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    rpc("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


def mark_watched(episode, started_watching_at):
    finished_watching_at = datetime.now()
    watch_duration = finished_watching_at - started_watching_at
    if watch_duration.seconds / episode.runtime.seconds >= 0.9:
        setplaycount(episode.kodiid, episode.playcount+1)
        log.info("%s: Marked as watched" % episode.code)
    else:
        log.info("%s: Skipped, only partially watched (%s vs. %s)" %
                 (episode.code, episode.runtime.seconds, watch_duration.seconds))


class Chrome(object):
    def connect(self,):
        self.chrome = Chromote(host="localhost", port=9222)
        self.tab = self.chrome.tabs[0]
        # if urlid not in self.driver.current_url:
            # self.login()

    def login(self):
        log.info("logging in")
        self.driver.get("https://www.netflix.com/Login")
        user = self.driver.find_element_by_id("email")
        user.clear()
        user.send_keys(settings["username"])
        passw = self.driver.find_element_by_id("password")
        passw.clear()
        passw.send_keys(settings["password"])
        btn = self.driver.find_element_by_id("login-form-contBtn")
        btn.click()
        self.driver.get(self.starturl)

    @property
    def url(self):
        return self.tab.url


class InternetExplorer(object):
    def connect(self, url):
        ShellWindowsCLSID = '{9BA05972-F6A8-11CF-A442-00A0C90A8F39}'
        ShellWindows = Dispatch(ShellWindowsCLSID)
        for shellwindow in ShellWindows:
            if win32gui.GetClassName(shellwindow.HWND) == 'IEFrame':
                self.ie = shellwindow
                break
        else:
            log.info("could not connect to Internet Explorer")

    def login(self):
        pass

    @property
    def url(self):
        return self.ie.LocationURL


def browse():
    pass


def live(channel):
    pass


class Player(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self)
        self.koalaplaying = False

    def onPlayBackStarted(self):
        playingfile = getplayingvideofile()
        if playingfile["file"].startswith(uni_join(const.libpath, "NRK")):
            self.koalaplaying = True
            self.remote = None
            if settings["browser"] == "Internet Explorer":
                self.browser = InternetExplorer()
            elif settings["browser"] == "Chrome":
                self.browser = Chrome()
            if settings["remote"]:
                self.remote = Remote()
                self.remote.run(browser=self.browser, player=self)

            # (self.browser.press_play())

            if playingfile["type"] == "episode":
                kodiid = playingfile["id"]
                thread = threading.Thread(target=self.mark_watched, args=[kodiid])
                thread.start()

    def monitor_watched(self, startkodiid):
        stored_episodes = get_stored_episodes(startkodiid)

        last_stored_url = self.browser.url
        current_urlid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", last_stored_url)
        episode_watching = stored_episodes[current_urlid]
        started_watching_at = datetime.now()
        while True:
            try:
                current_url = self.browser.url
            except:
                break

            if current_url == last_stored_url:
                xbmc.sleep(1000)
            else:
                new_urlid, is_episode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", current_url)
                if is_episode and new_urlid != episode_watching.urlid:
                    mark_watched(episode_watching, started_watching_at)

                    episode_watching = stored_episodes[new_urlid]
                    started_watching_at = datetime.now()
                last_stored_url = current_url

        mark_watched(episode_watching, started_watching_at)

    def onPlayBackEnded(self):
        if self.koalaplaying:
            self.koalaplaying = False
            if self.remote:
                self.remote.close()

if __name__ == "__main__":
    player = Player()
    xbmc.Monitor().waitForAbort()
