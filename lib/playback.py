#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, division)

import datetime as dt
from collections import namedtuple
import requests
import re
from multiprocessing.dummy import Process as Thread
import socket
import xbmc

import websocket
from chromote import Chromote
from pykeyboard import PyKeyboard
from pymouse import PyMouse

from . import constants as const
from . import utils
from . import kodi
from . import remote


class Player(object):
    def __init__(self):
        self.exceptions = (requests.exceptions.ConnectionError, socket.error,
                           websocket.WebSocketBadStatusException)
        self.tab = None
        self.stopped = False
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.player_coord = None
        x, y = self.m.screen_size()
        self.corner_coord = {'x': x, 'y': y}
        self.middle_coord = {"x": x // 2, "y": y // 2}

    def connect(self):
        try:
            self.browser = Chromote(host="localhost", port=9222)
        except requests.exceptions.ConnectionError:
            self.browser = Chromote(host="localhost", port=9222, internet_explorer=True)
        kodi.log("connected to %s: %s" % (self.browser.browsertype, self.browser))

        while not self.stopped:
            try:
                self.tab = next(tab for tab, title, url in self.browser.tabs if url != "about:blank" and "file://" not in url)
                break
            except StopIteration:
                xbmc.sleep(50)
        self.tab.connect_websocket()
        kodi.log("websocket connected: %s" % self.tab.url)

    def cleanup(self):
        if self.browser.browsertype == "ie":
            self.browser.close_ieadapter()
            kodi.log("closed ieadapter")
        if self.tab:
            self.tab.close_websocket()

    def get_player_coord(self):
        playerelement = self.tab.get_element_by_id("playerelement")
        while not playerelement.present:
            xbmc.sleep(100)
        rect = playerelement.rect
        self.player_coord = {"x": int((rect["left"] + rect["right"]) / 2),
                             "y": int((rect["top"] + rect["bottom"]) / 2)}

    def wait_player_start(self):
        for _ in range(120):
            if "ProgressTracker" in self.tab.get_element_by_tag_name("script")["src"]:
                break
            xbmc.sleep(500)

    def wait_for_url_change(self, stored_url=None):
        stored_url = self.tab.url
        while True:
            try:
                current_url = self.tab.url
                if current_url != stored_url:
                    return current_url
            except KeyError:
                # loading new page
                continue
            except (requests.exceptions.ConnectionError, socket.error,
                    websocket.WebSocketBadStatusException):
                # browser closed
                return None
            xbmc.sleep(1000)

    def playpause(self):
        self.k.tap_key(self.k.up_key)
        self.k.tap_key(self.k.space_key)

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
        log.info("fullscreen toggled")

    def stop(self):
        xbmc.Player().stop()
        self.stopped = True


class Session(object):
    def __init__(self):
        self.koala_playing = False

    def start(self):
        playingfile = self.get_playing_file()
        if not (playingfile["file"].startswith(uni_join(const.libpath, const.provider)) or
                playingfile["file"].startswith(uni_join(const.addonpath, "resources"))):
            return
        kodi.log("start onPlayBackStarted")
        self.koala_playing = True

        self.player = Player()

        self.remote = None
        if kodi.settings["remote"]:
            self.remote = remote.Remote()
            self.remote.run(player=self.player)

        self.player.connect()

        if "NRK nett-TV.htm" not in playingfile["file"]:
            self.player.get_player_coord()
            self.player.wait_player_start()
            self.player.toggle_fullscreen()

        if playingfile["type"] == "episode":
            thread = Thread(target=self.monitor_watched, args=[playingfile])
            thread.start()

        kodi.log("finished onPlayBackStarted")

    def end(self):
        if not self.koala_playing:
            return
        log.info("start onPlayBackEnded")
        try:
            if self.remote:
                self.remote.close()
            self.player.cleanup()
        finally:
            self.koala_playing = False
            log.info("finished onPlayBackEnded")

    def get_playing_file(self):
        active_player = kodi.rpc("Player.GetActivePlayers")[0]['playerid']
        playingfile = kodi.rpc("Player.GetItem", playerid=active_player,
                               properties=["season", "episode", "tvshowid", "file", "playcount", "runtime"])
        return playingfile["item"]

    def get_episodes(self, playingfile):
        Epinfo = namedtuple("Epinfo", "code kodiid playcount runtime")
        startkodiid = playingfile['id']
        tvshowid = playingfile["tvshowid"]
        tvshow_dict = kodi.rpc("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
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

        url = None
        current_urlid = starturlid
        episode_watching = stored_episodes[current_urlid]
        started_watching_at = dt.datetime.now()
        while self.koala_playing:
            url = self.player.wait_for_url_change(stored_url=url)
            if url is None:
                # browser closed
                break
            log.info("new url: %s" % url)
            new_urlid, is_episode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", url)
            if is_episode and new_urlid != current_urlid:
                self.mark_watched(episode_watching, started_watching_at)

                current_urlid = new_urlid
                episode_watching = stored_episodes[current_urlid]
                started_watching_at = dt.datetime.now()
                self.player.wait_player_start()
                self.player.toggle_fullscreen()

        self.mark_watched(episode_watching, started_watching_at)
        log.info("finished monitoring")

    def mark_watched(self, episode, started_watching_at):
        finished_watching_at = dt.datetime.now()
        watch_duration = finished_watching_at - started_watching_at
        if watch_duration.seconds / episode.runtime.seconds >= 0.9:
            kodi.rpc("VideoLibrary.SetEpisodeDetails", episodeid=episode.kodiid,
                     playcount=episode.playcount + 1, lastplayed=finished_watching_at.strftime("%d-%m-%Y %H:%M:%S"))
            kodi.log("%s: Marked as watched" % episode.code)
        else:
            kodi.log("%s: Skipped, only partially watched (%s vs. %s)" %
                     (episode.code, episode.runtime.seconds, watch_duration.seconds))


class Monitor(xbmc.Player):
    def __init__(self):
        kodi.log("launching playback service")
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
