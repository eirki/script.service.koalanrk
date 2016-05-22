#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, division)

import datetime as dt
from collections import namedtuple
import json
import requests
import re
import sys
from multiprocessing.dummy import Process as Thread
import socket
import xbmc

import websocket
from chromote import Chromote
from pykeyboard import PyKeyboard
from pymouse import PyMouse

from . import constants as const
from .utils import (uni_join, os_join)
from .xbmcwrappers import (log, settings, rpc)
from .remote import Remote
if const.os == "win":
    from win32com.client import Dispatch
    import pywintypes
    import win32gui


class Chrome(object):
    def __init__(self):
        self.errors = (requests.exceptions.ConnectionError, socket.error, websocket.WebSocketBadStatusException, AttributeError)
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.player_coord = None
        x, y = self.m.screen_size()
        self.corner_coord = {'x': x, 'y': y}
        self.middle_coord = {"x": x // 2, "y": y // 2}

    def _eval_js(self, exp):
        result = json.loads(self.tab.evaluate('document.%s' % exp))
        return result['result']['result']

    @property
    def url(self):
        return self.chrome.tabs[0].url

    @property
    def focused(self):
        return self._eval_js('hasFocus()')['value']

    def connect(self):
        self.chrome = Chromote(host="localhost", port=9222)
        self.tab = self.chrome.tabs[0]
        self.k.tap_key(self.k.tab_key)

    def close(self):
        if self.focused:
            self.k.press_key(self.k.control_key)
            self.k.tap_key("w")
            self.k.release_key(self.k.control_key)

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
            log.info("couldn't fint play")

        player_left = self._eval_js('getElementById("playerelement").getBoundingClientRect()["left"]')['value']
        player_width = self._eval_js('getElementById("playerelement").getBoundingClientRect()["width"]')['value']
        player_top = self._eval_js('getElementById("playerelement").getBoundingClientRect()["top"]')['value']
        player_height = self._eval_js('getElementById("playerelement").getBoundingClientRect()["height"]')['value']
        self.player_coord = {"x": player_left + (player_width // 2),
                             "y": player_top + (player_height // 2)}
        self.m.move(**self.player_coord)
        xbmc.sleep(200)
        self.m.click(n=1, **self.player_coord)

    def toggle_fullscreen(self):
        if self.player_coord:
            self.m.move(**self.player_coord)
            xbmc.sleep(200)
            self.m.click(n=2, **self.player_coord)
        else:
            self.m.click(n=2, **self.middle_coord)
        self.m.move(**self.corner_coord)

    def enter_fullscreen(self):
        if not self.player_coord:
            player_left = self._eval_js('getElementById("playerelement").getBoundingClientRect()["left"]')['value']
            player_width = self._eval_js('getElementById("playerelement").getBoundingClientRect()["width"]')['value']
            player_top = self._eval_js('getElementById("playerelement").getBoundingClientRect()["top"]')['value']
            player_height = self._eval_js('getElementById("playerelement").getBoundingClientRect()["height"]')['value']
            self.player_coord = {"x": player_left + (player_width // 2),
                                 "y": player_top + (player_height // 2)}
        log.info(self.player_coord)

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
        self.m.move(**self.player_coord)
        xbmc.sleep(200)
        self.m.click(n=2, **self.player_coord)
        self.m.move(**self.corner_coord)


class InternetExplorer(object):
    def __init__(self):
        self.errors = pywintypes.com_error, AttributeError
        self.m = PyMouse()
        self.player_coord = None
        x, y = self.m.screen_size()
        self.corner_coord = {'x': x, 'y': y}
        self.middle_coord = {"x": x // 2, "y": y // 2}

    @property
    def url(self):
        return self.ie.LocationURL

    def connect(self):
        xbmc.sleep(3000)
        for _ in range(30):
            iehandle = win32gui.GetForegroundWindow()
            shell = Dispatch("Shell.Application")
            for win in shell.Windows():
                if win.hwnd == iehandle:
                    self.ie = win
                    return
            xbmc.sleep(100)
        log.info("could not connect to Internet Explorer")

    def close(self):
        self.ie.quit()

    def trigger_player(self):
        while self.ie.busy:
            xbmc.sleep(100)
        log.info("triggering player")
        for _ in range(10):
            playicon = next((elem for elem in self.ie.document.body.all.tags("span") if elem.className == 'play-icon'), None)
            if playicon:
                playicon.click()
                rect = playicon.getBoundingClientRect()
                self.player_coord = {"x": rect.left, "y": rect.top}
                break
            else:
                xbmc.sleep(1000)
        else:
            log.info("couldn't fint play")
            try:
                playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement")
                rect = playerelement.getBoundingClientRect()
                self.player_coord = {"x": (rect.left + rect.right // 2), "y": (rect.top + rect.bottom // 2)}
                self.m.click(button=1, n=1, **self.player_coord)
            except StopIteration:
                log.info("couldn't find playerelement")
                self.m.click(button=1, n=1, **self.middle_coord)

    def toggle_fullscreen(self):
        if self.player_coord:
            self.m.move(**self.player_coord)
            xbmc.sleep(200)
            self.m.click(n=2, **self.player_coord)
        else:
            self.m.click(n=2, **self.middle_coord)
        self.m.move(**self.corner_coord)

    def enter_fullscreen(self):
        while self.ie.busy:
            xbmc.sleep(100)
        if not self.player_coord:
            try:
                playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement1")
                rect = playerelement.getBoundingClientRect()
                self.player_coord = {"x": (rect.left + rect.right // 2), "y": (rect.top + rect.bottom // 2)}
            except StopIteration:
                log.info("couldn't find playerelement")
                self.player_coord = self.middle_coord

        log.info("waitong for player ready for fullscreen")
        for _ in range(10):
            try:
                next((elem for elem in self.ie.document.head.all.tags("script") if "ProgressTracker" in elem.getAttribute("src")))
                break
            except StopIteration:
                xbmc.sleep(1000)
        else:
            log.info("couldnt find progressbar, don't know if playback started")

        log.info("double clicking")

        self.m.move(**self.player_coord)
        xbmc.sleep(200)
        self.m.click(n=2, **self.player_coord)
        self.m.move(**self.corner_coord)


class Session(object):
    def __init__(self):
        self.koala_playing = False

    def start(self):
        playingfile = self.getplayingvideofile()
        if not (playingfile["file"].startswith(uni_join(const.libpath, const.provider)) or
                playingfile["file"] in [uni_join(const.addonpath, "resources", "NRK1.htm"),
                                        uni_join(const.addonpath, "resources", "NRK2.htm"),
                                        uni_join(const.addonpath, "resources", "NRK3.htm"),
                                        uni_join(const.addonpath, "resources", "NRK Super.htm"),
                                        uni_join(const.addonpath, "resources", "NRK nett-TV.htm"),
                                        uni_join(const.addonpath, "resources", "Fantorangen BarneTV.htm"),
                                        uni_join(const.addonpath, "resources", "BarneTV.htm")]):
            return
        log.info("start onPlayBackStarted")
        self.koala_playing = True

        if const.os == "win" and self.ie_active():
            self.browser = InternetExplorer()
        else:
            self.browser = Chrome()

        self.remote = None
        if settings["remote"]:
            self.remote = Remote()
            self.remote.run(browser=self.browser)

        self.browser.connect()

        if playingfile["type"] in ["episode", "movie"]:
            self.browser.trigger_player()

        if "NRK nett-TV.htm" not in playingfile["file"]:
            self.browser.enter_fullscreen()

        if playingfile["type"] == "episode":
            thread = Thread(target=self.monitor_watched, args=[playingfile])
            thread.start()

        log.info("finished onPlayBackStarted")

    def end(self):
        if not self.koala_playing:
            return
        log.info("start onPlayBackEnded")
        if self.remote:
            self.remote.close()
        self.koala_playing = False
        log.info("finished onPlayBackEnded")

    def getplayingvideofile(self):
        if xbmc.Player().isPlayingAudio():
            playerid = 0
        elif xbmc.Player().isPlayingVideo():
            playerid = 1
        playingfile = rpc("Player.GetItem", playerid=playerid,
                          properties=["season", "episode", "tvshowid", "file", "playcount", "runtime"])
        return playingfile["item"]

    def ie_active(self):
        for _ in range(30):
            cur_hwnd = win32gui.GetForegroundWindow()
            win_title = win32gui.GetWindowText(cur_hwnd).decode(sys.getfilesystemencoding())
            if "explorer" in win_title.lower():
                log.info("ie active")
                return True
            elif "chrome" in win_title.lower():
                log.info("chrome active")
                return False
            elif "kodi" in win_title.lower() and not xbmc.Player().isPlaying():
                log.info("playback cancelled")
            xbmc.sleep(1000)
        else:
            raise Exception("could not find player")

    def get_episodes(self, playingfile):
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
            runtime = dt.timedelta(seconds=episode['runtime'])
            with open(episode['file'], 'r') as txt:
                urlid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", txt.read())
            stored_episodes[urlid] = Epinfo(epcode, kodiid, playcount, runtime)
            if kodiid == startkodiid:
                starturlid = urlid
        return starturlid, stored_episodes

    def monitor_watched(self, playingfile):
        log.info("starting monitoring")
        starturlid, stored_episodes = self.get_episodes(playingfile)
        log.info(stored_episodes)

        last_stored_url = self.browser.url
        current_urlid = starturlid
        episode_watching = stored_episodes[current_urlid]
        started_watching_at = dt.datetime.now()
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
                if is_episode and new_urlid != current_urlid:
                    self.mark_watched(episode_watching, started_watching_at)

                    episode_watching = stored_episodes[new_urlid]
                    started_watching_at = dt.datetime.now()
                    current_urlid = new_urlid
                last_stored_url = current_url

        self.mark_watched(episode_watching, started_watching_at)
        log.info("finished monitoring")

    def mark_watched(self, episode, started_watching_at):
        finished_watching_at = dt.datetime.now()
        watch_duration = finished_watching_at - started_watching_at
        if watch_duration.seconds / episode.runtime.seconds >= 0.9:
            rpc("VideoLibrary.SetEpisodeDetails", episodeid=episode.kodiid,
                playcount=episode.playcount+1, lastplayed=finished_watching_at.strftime("%d-%m-%Y %H:%M:%S"))
            log.info("%s: Marked as watched" % episode.code)
        else:
            log.info("%s: Skipped, only partially watched (%s vs. %s)" %
                     (episode.code, episode.runtime.seconds, watch_duration.seconds))


class Monitor(xbmc.Player):
    def __init__(self):
        log.info("launching playback service")
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
    filenames = {
        "nrk1": "NRK1.htm",
        "nrk2": "NRK2.htm",
        "nrk3": "NRK3.htm",
        "nrksuper": "NRK Super.htm",
        "browse": "NRK nett-TV.htm",
        "fantorangen": "Fantorangen BarneTV.htm",
        "barnetv": "BarneTV.htm",
    }
    xbmc.Player().play(os_join(const.addonpath, "resources", filenames[channel]))
