#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import re
from datetime import (timedelta, datetime)
from collections import namedtuple
import json
import requests
from multiprocessing.dummy import Process as Thread
import xbmc

from chromote import Chromote
from lib import constants as const
from lib.utils import (uni_join, os_join)
from lib.xbmcwrappers import (log, settings, rpc)
if const.os == "win":
    from lib import win32hack
    win32hack.run()
    from win32com.client import Dispatch
    import pywintypes
    import win32gui
from lib.remote import Remote
from lib.PyUserInput.pymouse import PyMouse


def getplayingvideofile():
    if xbmc.Player().isPlayingAudio():
        # log.info("Audio file playing")
        playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=0)
    if xbmc.Player().isPlayingVideo():
        # log.info("Video file playing")
        playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=1)
    # log.info("Playing: %s" % playingfile["item"])
    if "item" in playingfile:
        playingfile = playingfile["item"]
    return playingfile


def get_episodes(playingfile):
    Epinfo = namedtuple("Epinfo", "code kodiid playcount runtime")
    startkodiid = playingfile['id']
    tvshowid = playingfile["tvshowid"]
    tvshow_dict = rpc("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
                      "playcount", "season", "episode", "file", "runtime"])
    stored_episodes = {}
    for episode in tvshow_dict['episodes']:
        epcode = 'S%02dE%02d' % (episode['season'], episode['episode'])
        kodiid = episode['episodeid']
        playcount = episode['playcount']
        runtime = timedelta(seconds=episode['runtime'])
        with open(episode['file'], 'r') as txt:
            urlid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", txt.read())
        stored_episodes[urlid] = Epinfo(epcode, kodiid, playcount, runtime)
        if kodiid == startkodiid:
            starturlid = urlid
    return starturlid, stored_episodes


def mark_watched(episode, started_watching_at):
    finished_watching_at = datetime.now()
    watch_duration = finished_watching_at - started_watching_at
    if watch_duration.seconds / episode.runtime.seconds >= 0.9:
        rpc("VideoLibrary.SetEpisodeDetails", episodeid=episode.kodiid,
            playcount=episode.playcount+1, lastplayed=finished_watching_at.strftime("%d-%m-%Y %H:%M:%S"))
        log.info("%s: Marked as watched" % episode.code)
    else:
        log.info("%s: Skipped, only partially watched (%s vs. %s)" %
                 (episode.code, episode.runtime.seconds, watch_duration.seconds))


class Chrome(object):
    def __init__(self):
        self.errors = requests.exceptions.ConnectionError

    def connect(self):
        self.chrome = Chromote(host="localhost", port=9222)
        self.tab = self.chrome.tabs[0]

    @property
    def url(self):
        return self.chrome.tabs[0].url

    def _eval_js(self, exp):
        result = json.loads(self.tab.evaluate('document.%s' % exp))
        return result['result']['result']

    def trigger_player(self):
        log.info("triggering player")
        for _ in range(10):
            player_loaded = self._eval_js('getElementsByClassName("play-icon")[0]')['type'] != "undefined"
            if player_loaded:
                self._eval_js('getElementsByClassName("play-icon")[0].click()')
                break
            else:
                xbmc.sleep(1000)
        else:
            raise "couldn't find play button!"

    def enter_fullscreen(self):
        player_left = self._eval_js('getElementById("playerelement").getBoundingClientRect()["left"]')['value']
        player_width = self._eval_js('getElementById("playerelement").getBoundingClientRect()["width"]')['value']
        player_top = self._eval_js('getElementById("playerelement").getBoundingClientRect()["top"]')['value']
        player_height = self._eval_js('getElementById("playerelement").getBoundingClientRect()["height"]')['value']
        player_coord = {"x": int(player_left+(player_width/2)),
                        "y": int(player_top+(player_height/2))}
        log.info(player_coord)

        for _ in range(10):
            playback_started = "ProgressTracker" in self._eval_js('getElementsByTagName("script")[0].getAttribute("src")')['value']
            if playback_started:
                log.info("playback started")
                break
            else:
                xbmc.sleep(1000)
        else:
            log.info("couldnt find progressbar, not sure if playback started")

        log.info("double clicking")
        m = PyMouse()
        m.move(**player_coord)
        xbmc.sleep(200)
        m.click(n=2, **player_coord)


class InternetExplorer(object):
    def __init__(self):
        self.errors = pywintypes.com_error, AttributeError
        self.m = PyMouse()

    def connect(self):
        for _ in range(10):
            ShellWindowsCLSID = '{9BA05972-F6A8-11CF-A442-00A0C90A8F39}'
            ShellWindows = Dispatch(ShellWindowsCLSID)
            ie = next((shellwindow for shellwindow in ShellWindows if win32gui.GetClassName(shellwindow.HWND) == 'IEFrame'), None)
            if ie:
                self.ie = ie
                break
            else:
                xbmc.sleep(1000)
        else:
            log.info("could not connect to Internet Explorer")

    @property
    def url(self):
        return self.ie.LocationURL

    def trigger_player(self):
        log.info("triggering player")
        while self.ie.busy:
            xbmc.sleep(100)
        try:
            playicon = next(elem for elem in self.ie.document.body.all.tags("span") if elem.className == 'play-icon')
            playicon.click()
            log.info("clicked play")
            rect = playicon.getBoundingClientRect()
            self.player_coord = {"x": rect.left, "y": rect.top}
        except StopIteration:
            log.info("couldn't fint play")
            playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement")
            rect = playerelement.getBoundingClientRect()
            self.player_coord = {"x": (int(rect.left+rect.right/2)), "y": (int(rect.top+rect.bottom/2))}
            self.m.click(button=1, n=1, **self.player_coord)

    def enter_fullscreen(self):
        if not self.player_coord:
            while self.ie.busy:
                xbmc.sleep(100)
            playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement")
            rect = playerelement.getBoundingClientRect()
            self.player_coord = {"x": (int(rect.left+rect.right/2)), "y": (int(rect.top+rect.bottom/2))}

        log.info("waitong for player ready for fullscreen")
        for _ in range(10):
            playback_started = next((elem for elem in self.ie.document.head.all.tags("script")
                                     if "ProgressTracker" in elem.getAttribute("src")), False)
            if playback_started:
                break
            xbmc.sleep(1000)
        else:
            log.info("couldnt find progressbar, don't know if playback started")

        log.info("double clicking")

        self.m.move(**self.player_coord)
        xbmc.sleep(200)
        self.m.click(n=2, **self.player_coord)


class Session(object):
    def start(self):
        log.info("start onPlayBackStarted")
        playingfile = getplayingvideofile()
        if not playingfile["file"].startswith(uni_join(const.libpath, const.provider)):
            self.koala_playing = False
            return
        self.koala_playing = True
        self.remote = None
        if settings["remote"]:
            self.remote = Remote()
            self.remote.run()

        if settings["browser"] == "Internet Explorer":
            self.browser = InternetExplorer()
        elif settings["browser"] == "Chrome":
            self.browser = Chrome()
        self.browser.connect()
        self.browser.trigger_player()
        self.browser.enter_fullscreen()

        if playingfile["type"] == "episode":
            thread = Thread(target=self.monitor_watched, args=[playingfile])
            thread.start()

        log.info("finished onPlayBackStarted")

    def monitor_watched(self, playingfile):
        log.info("starting monitoring")
        starturlid, stored_episodes = get_episodes(playingfile)
        log.info(stored_episodes)

        last_stored_url = self.browser.url
        current_urlid = starturlid
        episode_watching = stored_episodes[current_urlid]
        started_watching_at = datetime.now()
        while self.koala_playing:
            try:
                current_url = self.browser.url
            except self.browser.errors:
                break

            if current_url == last_stored_url:
                xbmc.sleep(1000)
            else:
                log.info("new url: %s" % current_url)
                new_urlid, is_episode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", current_url)
                if is_episode and new_urlid != episode_watching.urlid:
                    log.info("is_episode")
                    log.info(new_urlid)
                    mark_watched(episode_watching, started_watching_at)

                    episode_watching = stored_episodes[new_urlid]
                    started_watching_at = datetime.now()
                last_stored_url = current_url

        mark_watched(episode_watching, started_watching_at)
        log.info("finished monitoring")

    def end(self):
        log.info("start onPlayBackEnded")
        if not self.koala_playing:
            return
        if self.remote:
            self.remote.close()
        self.koala_playing = False
        log.info("finished onPlayBackEnded")


class PlayerMonitor(xbmc.Player):
    def __init__(self):
        self.queue = []
        xbmc.Player.__init__(self)

    def add_to_queue(self, func):
        self.queue.append(func)
        if self.queue[0] is func:
            while self.queue:
                try:
                    self.queue[0]()
                finally:
                    self.queue.pop(0)

    def onPlayBackStarted(self):
        self.session = Session()
        self.add_to_queue(self.session.start)

    def onPlayBackEnded(self):
        self.add_to_queue(self.session.end)


def live(channel):
    xbmc.Player().play(os_join(const.addonpath, "resources", "%s.htm" % channel))


if __name__ == "__main__":
    log.info("launching playback service")
    player_monitor = PlayerMonitor()
    xbmc.Monitor().waitForAbort()
    log.info("closing playback service")
