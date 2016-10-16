#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import datetime as dt
from collections import namedtuple
import requests
import re
from threading import Thread
import traceback
import socket
import sys
import xbmc

import websocket
from chromote import Chromote
from pykeyboard import PyKeyboard
from pymouse import PyMouse

from lib import constants as const
from lib import utils
from lib import kodi
from lib import remote


MediaItem = namedtuple("MediaItem", "name kodiid playcount runtime")


class StoppedException(Exception):
    pass


class StopEvent(object):
    def __init__(self):
        self.is_set = False

    def wait(self):
        while not self.is_set:
            xbmc.sleep(500)

    def check(self):
        if self.is_set:
            raise StoppedException

    def set(self):
        self.is_set = True


class Player(object):
    def __init__(self, stop_event):
        self.exceptions = (StoppedException, requests.exceptions.ConnectionError, socket.error,
                           websocket.WebSocketBadStatusException, websocket.WebSocketConnectionClosedException)
        self.stop_event = stop_event
        self.browser = None
        self.tab = None
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

        while not self.stop_event.check():
            try:
                self.tab = next(tab for tab, title, url in self.browser.tabs if url != "about:blank" and "file://" not in url)
                break
            except StopIteration:
                xbmc.sleep(200)
        self.tab.connect_websocket()
        kodi.log("websocket connected: %s" % self.tab.url)

    def disconnect(self):
        if self.browser and self.browser.browsertype == "ie":
            self.browser.close_ieadapter()
            kodi.log("closed ieadapter")
        if self.tab:
            self.tab.close_websocket()

    def start(self):
        self.get_player_coord()
        self.wait_player_start()
        self.toggle_fullscreen()

    def get_player_coord(self):
        playerelement = self.tab.get_element_by_id("playerelement")
        while not (self.stop_event.check() or playerelement.present):
            xbmc.sleep(100)
        rect = playerelement.rect
        self.player_coord = {"x": int((rect["left"] + rect["right"]) / 2),
                             "y": int((rect["top"] + rect["bottom"]) / 2)}

    def wait_player_start(self):
        for _ in range(120):
            src = self.tab.get_element_by_tag_name("script")["src"]
            if self.stop_event.check() or (src is not None and "ProgressTracker" in src):
                break
            xbmc.sleep(500)

    def wait_for_new_episode(self, starting_urlid):
        starting_url = self.tab.url
        while not self.stop_event.is_set:
            try:
                xbmc.sleep(1000)
                current_url = self.tab.url
                if current_url == starting_url:
                    # no url change
                    continue
                is_episode_page = re.match(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', current_url)
                if not is_episode_page:
                    continue
                new_urlid = is_episode_page.group(1).lower()
                if new_urlid != starting_urlid:
                    # new episode started
                    self.wait_player_start()
                    self.toggle_fullscreen()
                    return new_urlid
            except KeyError:
                # loading new page
                continue
            except self.exceptions:
                # browser closed
                return None

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

    def stop(self):
        xbmc.Player().stop()
        self.stop_event.set()


class Session(object):
    def __init__(self):
        self.stop_event = StopEvent()
        self.remote = None
        self.player = None

    def setup(self):
        playingfile = self.get_playing_file()
        if not playingfile["file"].startswith((utils.uni_join(const.libpath, const.provider),
                                               utils.uni_join(const.addonpath, "resources"))):
            return
        try:
            kodi.log("Start playback setup")

            self.player = Player(stop_event=self.stop_event)

            if kodi.settings["remote"]:
                self.remote = remote.Remote()
                self.remote.run(player=self.player)

            self.player.connect()

            if not playingfile["file"].endswith(("NRK nett-TV.htm", "NRK Super.htm")):
                self.player.start()

            if playingfile["type"] == "episode":
                Thread(target=self.monitor_episodes_progress, args=[playingfile]).start()
            elif playingfile["type"] == "movie":
                Thread(target=self.monitor_movie_progress, args=[playingfile]).start()

            kodi.log("Finished playback setup")

        except self.player.exceptions:
            pass

        except:
            kodi.log("Exception occured during playback\n%s" % traceback.format_exc().decode(sys.getfilesystemencoding()))

        finally:
            self.stop_event.wait()

            kodi.log("Start playback cleanup")
            if self.remote:
                self.remote.close()
            if self.player:
                self.player.disconnect()
            kodi.log("Finish playback cleanup")

    def get_playing_file(self):
        active_player = kodi.rpc("Player.GetActivePlayers")[0]['playerid']
        playingfile = kodi.rpc("Player.GetItem", playerid=active_player,
                               properties=["season", "episode", "tvshowid", "file", "playcount", "runtime"])
        return playingfile["item"]

    def get_episodes(self, playingfile):
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
                urlid = re.match(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)\?autostart=true.*', txt.read()).group(1).lower()
            stored_episodes[urlid] = MediaItem(epcode, kodiid, playcount, runtime)
            if kodiid == startkodiid:
                starturlid = urlid
        return starturlid, stored_episodes

    def mark_watched(self, mediaitem, started_watching_at):
        finished_watching_at = dt.datetime.now()
        watch_duration = finished_watching_at - started_watching_at
        if 0 in (mediaitem.runtime.seconds, watch_duration.seconds):
            return
        if watch_duration.seconds / mediaitem.runtime.seconds >= 0.9:
            kodi.rpc("VideoLibrary.SetEpisodeDetails", episodeid=mediaitem.kodiid,
                     playcount=mediaitem.playcount + 1, lastplayed=finished_watching_at.strftime("%d-%m-%Y %H:%M:%S"))
            kodi.log("%s: Marked as watched" % mediaitem.name)
        else:
            kodi.log("%s: Skipped, only partially watched (%s vs. %s)" %
                     (mediaitem.name, mediaitem.runtime.seconds, watch_duration.seconds))

    def monitor_episodes_progress(self, playingfile):
        kodi.log("Starting episode progress monitoring")
        first_urlid, stored_episodes = self.get_episodes(playingfile)

        current_urlid = first_urlid
        episode_watching = stored_episodes[current_urlid]
        started_watching_at = dt.datetime.now()
        while not self.stop_event.is_set:
            new_urlid = self.player.wait_for_new_episode(starting_urlid=current_urlid)
            if new_urlid is None:
                break  # browser closed
            if episode_watching:
                self.mark_watched(episode_watching, started_watching_at)

            kodi.log("new urlid: %s" % new_urlid)
            current_urlid = new_urlid
            episode_watching = stored_episodes.get(current_urlid)
            started_watching_at = dt.datetime.now()

        self.mark_watched(episode_watching, started_watching_at)
        kodi.log("finished monitoring")

    def monitor_movie_progress(self, playingfile):
        kodi.log("starting monitoring")
        movie = MediaItem(name=playingfile["label"], kodiid=playingfile["id"], playcount=playingfile["playcount"],
                          runtime=dt.timedelta(seconds=playingfile["runtime"]))
        started_watching_at = dt.datetime.now()
        self.stop_event.wait()
        self.mark_watched(movie, started_watching_at)
        kodi.log("finished monitoring")


class PlaybackManager(xbmc.Player):
    def __init__(self):
        kodi.log("Launching playback service")
        self.queue = []
        xbmc.Player.__init__(self)

    def onPlayBackStarted(self):
        self.session = Session()
        # kodi.log("Manager: onPlayBackStarted %s" % self.session)
        self.queue.append(self.session.setup)
        if len(self.queue) > 1:
            # setup func for other session is already running
            # kodi.log("Manager: waiting %s\nQueue: %s" % (self.session.setup, self.queue))
            return
        while self.queue:
            try:
                # kodi.log("Manager: starting %s\nQueue: %s" % (self.queue[0], self.queue))
                self.queue[0]()
            except:
                pass
            finally:
                # kodi.log("Manager: finished %s\nQueue: %s" % (self.queue[0], self.queue))
                self.queue.pop(0)
        # kodi.log("Manager: finished onPlayBackStarted")

    def onPlayBackEnded(self):
        # kodi.log("Manager: onPlayBackEnded %s\nQueue: %s" % (self.session, self.queue))
        self.session.stop_event.set()
        # kodi.log("Manager: finished onPlayBackEnded")


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
    xbmc.Player().play(utils.os_join(const.addonpath, "resources", filenames[channel]))
