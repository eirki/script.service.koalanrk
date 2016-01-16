#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import arrow
import re
import xbmc
from datetime import timedelta
import sys
import xbmcgui
import xbmcplugin
from collections import defaultdict, namedtuple
import subprocess
import os
import json

from .selenium import webdriver
from .selenium.webdriver.common.keys import Keys
from .selenium.webdriver.common.by import By
from .selenium.webdriver.support.ui import WebDriverWait
from .selenium.webdriver.support import expected_conditions as EC
from .selenium.common.exceptions import TimeoutException
from .selenium.webdriver.common.action_chains import ActionChains
from . import selenium

from utils import (settings, log, os_join, rpc, const)

# def getplayingvideofile():
#     if xbmc.Player().isPlayingAudio():
#         log.info("Audio file playing")
#         playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=0)
#     if xbmc.Player().isPlayingVideo():
#         log.info("Video file playing")
#         playingfile = rpc("Player.GetItem", properties=["season", "episode", "tvshowid", "file"], playerid=1)
#     log.info("Playing: %s" % playingfile["item"])
#     if "item" in playingfile:
#         playingfile = playingfile["item"]
#     return playingfile


def gen_epdict(kodiid):
    playingfile = rpc("VideoLibrary.GetEpisodeDetails", episodeid=int(kodiid), properties=["tvshowid", "season", "episode"])["episodedetails"]
    print playingfile
    tvshowid = playingfile["tvshowid"]
    tvshow_dict = rpc("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
                      "playcount", "season", "episode", "file", "runtime"])
    epdict = {}
    for episode in tvshow_dict['episodes']:
        epcode = 'S%02dE%02d' % (episode['season'], episode['episode'])
        kodiid = episode['episodeid']
        playcount = episode['playcount']
        runtime = episode['runtime']
        with open(episode['file'], 'r') as txt:
            nrkid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", txt.read()).strip()
        epdict[nrkid] = [epcode, kodiid, playcount, runtime]
    log.info("epdict: %s" % epdict)
    return epdict


def mark_watched(epdict, watched):
    log.info("mark_watched")
    for nrkid, watchedduration in watched:
        if nrkid in epdict:
            epcode, kodiid, playcount, runtime = epdict[nrkid]
            runtime = timedelta(seconds=runtime)
            log.info("%s runtime: %s" % (epcode, runtime.seconds))
            if watchedduration.seconds / runtime.seconds >= 0.9:
                addplaycount(kodiid, playcount)
                log.info("%s: Marked as watched" % epcode)
            else:
                log.info("%s: Skipped, only partially watched (%s vs. %s)" % (epcode, runtime.seconds, watchedduration.seconds))
            #     add partially watched flag?
        else:
            log.info("nrkid not found in epdict: %s" % nrkid)


def addplaycount(kodiid, playcount):
    playcount += 1
    now = arrow.now().format("%d-%m-%Y %H:%M:%S")
    rpc("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


def getremotemapping():
    try:
        with open(os_join(const.userdatafolder, "remotemapping.json")) as j:
            remotemapping = defaultdict(str, json.load(j))
    except IOError:
        remotemapping = defaultdict(str)
    controls = [remotemapping["Play"], remotemapping["Pause"], remotemapping["Stop"],
                remotemapping["Forward"], remotemapping["Rewind"], remotemapping["Continue Playing at prompt"]]
    return controls


class SeleniumDriver(object):
    def __init__(self):
        self.browser = settings["browser"]

    def open(self, url):
        if self.browser == "Internet Explorer":
            driverpath = os_join(const.addonpath, "resources", "IEDriverServer_Win32_2.48.0")
            log.info(driverpath)
            os.environ["PATH"] = "".join([os.environ["PATH"], ";", driverpath])
            self.driver = webdriver.Ie(capabilities={
                "initialBrowserUrl": url,
                "ignoreZoomSetting": True,
                "ignoreProtectedModeSettings": True,
                })
            window_size = self.driver.get_window_size()
            if not (window_size['width'] == 1920 and window_size['height']) == 1080:
                body = self.driver.find_element_by_tag_name("body")
                body.send_keys(Keys.F11)
        elif self.browser == "Chrome":
            options = selenium.webdriver.chrome.options.Options()
            options.add_experimental_option('excludeSwitches', ['disable-component-update'])
            options.add_argument('--kiosk')
            options.add_argument("--profile-directory=Eirik")
            d = "C:/Users/Eirki/AppData/Local/Google/Chrome/User Data/Default"
            options.add_argument("--user-data-dir=%s" % d)
            self.driver = webdriver.Chrome("D:/Dropbox/Programmering/HTPC/selenium/chromedriver.exe", chrome_options=options)
        self.trigger_player()

    def trigger_player(self):
        try:
            playbutton = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "play-icon")))
            playbutton.click()
            playerelement = self.driver.find_element_by_id("playerelement")
        except TimeoutException:
            playerelement = self.driver.find_element_by_id("playerelement")
            playerelement.click()

        while "ProgressTracker" not in self.driver.find_elements_by_tag_name("script")[0].get_attribute('src'):
            xbmc.sleep(100)

        playerelement = self.driver.find_element_by_id("playerelement")
        actionChains = ActionChains(self.driver)
        actionChains.double_click(playerelement).perform()

    def gather_urls_wait_for_exit(self):
        log.info("setting up url gathering")
        self.watched = []
        found = False
        while not found:
            current_nrkid, found = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.driver.current_url)
            xbmc.sleep(1000)
        startwatch = arrow.now()
        last_stored_url = self.driver.current_url

        WatchedEpisode = namedtuple("Watched", "id duration")
        log.info("gathering urls")
        while True:
            try:
                if self.driver.current_url != last_stored_url:
                    new_nrkid, is_newepisode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.driver.current_url)
                    if is_newepisode and current_nrkid != new_nrkid:
                        duration = arrow.now() - startwatch
                        self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))

                        current_nrkid = new_nrkid
                        startwatch = arrow.now()
                    last_stored_url = self.driver.current_url
                    log.info("watched: %s:" % self.watched)
            except (selenium.common.exceptions.WebDriverException, AttributeError):
                duration = arrow.now() - startwatch
                self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
                break
            xbmc.sleep(1000)
        log.info("finished gathering urls")
        log.info("watched: %s" % self.watched)

    def close(self):
        log.info("ensuring selenium closed")
        if self.driver:
            self.driver.quit()
        self.driver = None


def player_wrapper(play_func):
    def wrapper(url):
        xbmc.executebuiltin("ActivateWindow(busydialog)")
        listitem = xbmcgui.ListItem(path=os_join(const.addonpath, "resources", "fakeVid.mp4"))
        xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listitem)
        try:
            play_func(url)
        finally:
            xbmc.PlayList(xbmc.PLAYLIST_VIDEO).clear()
            xbmc.executebuiltin("Dialog.Close(busydialog)")
    return wrapper


@player_wrapper
def play(url):
    log.info("playbackstart starting")
    browser = SeleniumDriver()
    browser.open(url)
    remoteprocess = None
    if settings["remote"]:
        mapping = getremotemapping()
        log.info("Launching remote utility")
        remoteprocess = subprocess.Popen([const.ahkexe, os_join(const.ahkfolder, "remote.ahk"), settings["browser"]]+mapping)
    kodiid = xbmc.getInfoLabel('ListItem.DBID')
    epdict = gen_epdict(kodiid)
    log.info("playbackstart finished")

    browser.gather_urls_wait_for_exit()

    log.info("playbackend starting")
    log.info(browser.watched)
    browser.close()
    if remoteprocess:
        remoteprocess.terminate()
    mark_watched(epdict, browser.watched)
    log.info("playbackend finished")
