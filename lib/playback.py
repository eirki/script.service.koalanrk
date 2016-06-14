#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, division)

import datetime as dt
from collections import namedtuple
import json
import requests
import re
import subprocess
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


class Player(object):
    def __init__(self):
        self.errors = (requests.exceptions.ConnectionError, socket.error,
                       websocket.WebSocketBadStatusException, AttributeError, IndexError)
        self.ieadapter = None
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.player_coord = None
        x, y = self.m.screen_size()
        self.corner_coord = {'x': x, 'y': y}
        self.middle_coord = {"x": x // 2, "y": y // 2}

    def _eval_js(self, exp):
        result = json.loads(self.tab.evaluate('document.%s' % exp))
        try:
            return result['result']['result']
        except KeyError:
            log.info(result)
            raise

    def connect(self):
        try:
            self.browser = Chromote(host="localhost", port=9222)
            self.browsertype = "chrome"
        except requests.exceptions.ConnectionError:
            adapterpath = os_join(const.homefolder, "addons", "script.module.chromote", "resources",
                                  "IEDiagnosticsAdapter", "IEDiagnosticsAdapter.exe")
            self.ieadapter = subprocess.Popen(adapterpath, shell=True)
            self.browser = Chromote(host="localhost", port=9222)
            self.browsertype = "ie"

        while True:
            try:
                self.tab = next(tab for tab in self.browser.tabs if tab.url != "about:blank" and "file://" not in tab.url)
                break
            except StopIteration:
                xbmc.sleep(50)
        self.tab.connect_websocket()
        log.info("websocket connected: %s" % self.tab.url)

    def close(self):
        if self.ieadapter:
            self.ieadapter.terminate()

    @property
    def url(self):
        return self._eval_js("URL")["value"]

    def playpause(self):
        self.k.tap_key(self.k.up_key)
        self.k.tap_key(self.k.space_key)

    def enter_fullscreen(self):
        player_left = self._eval_js('getElementById("playerelement").getBoundingClientRect()["left"]')['value']
        player_width = self._eval_js('getElementById("playerelement").getBoundingClientRect()["width"]')['value']
        player_top = self._eval_js('getElementById("playerelement").getBoundingClientRect()["top"]')['value']
        player_height = self._eval_js('getElementById("playerelement").getBoundingClientRect()["height"]')['value']
        self.player_coord = {"x": int(player_left + (player_width / 2)),
                             "y": int(player_top + (player_height / 2))}
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
    def forward(self):
        self.k.tap_key(self.k.right_key)

    def rewind(self):
        self.k.tap_key(self.k.left_key)

    def toggle_fullscreen(self):
        coord = self.player_coord if self.player_coord else self.middle_coord
        self.m.move(**coord)
        xbmc.sleep(200)
        self.m.click(n=2, **coord)
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

        self.player = Player()

        self.remote = None
        if settings["remote"]:
            self.remote = Remote()
            self.remote.run(player=self.player)

        self.player.connect()

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
