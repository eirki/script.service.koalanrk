#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import re
from datetime import (timedelta, datetime)
import sys
from collections import namedtuple
import traceback
import xbmcgui
import xbmcplugin
import xbmc

import socket
import httplib
import urllib2

from lib.selenium import webdriver
from lib.selenium.webdriver.common.by import By
from lib.selenium.webdriver.support.ui import WebDriverWait
from lib.selenium.webdriver.support import expected_conditions as EC
from lib.selenium.common.exceptions import (TimeoutException, WebDriverException)
from lib.selenium.webdriver.common.action_chains import ActionChains

from win32com.client import Dispatch
import pywintypes
import win32gui

from .PyUserInput.pymouse import PyMouse
from . import constants as const
from .utils import os_join
from .remote import Remote
from .xbmcwrappers import (log, settings, rpc)


class NowPlayingOverly(xbmcgui.WindowXMLDialog):
    def __new__(cls):
        return super(NowPlayingOverly, cls).__new__(cls, "DialogKaiToast.xml", const.addonpath)

    def __init__(self):
        super(NowPlayingOverly, self).__init__()

    def set_args(self, title, duration):
        self.title = title
        duration = timedelta(minutes=int(duration))
        self.finish_time = datetime.now() + duration

    def onInit(self):
        self.getControl(400).setImage(os_join(const.addonpath, "resources", "play.png"))
        self.getControl(401).setLabel(self.title)
        self.getControl(402).setLabel("Finish time: {:%H:%M:%S}".format(self.finish_time))

    def close(self):
        del self


def gen_epdict(kodiid):
    playingfile = rpc("VideoLibrary.GetEpisodeDetails", episodeid=int(kodiid), properties=["tvshowid", "season", "episode"])
    tvshowid = playingfile["episodedetails"]["tvshowid"]
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
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    rpc("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


class SeleniumDriver(object):
    def open(self, url):
        self.seleniumerrors = (AttributeError, socket.error, httplib.CannotSendRequest,
                               WebDriverException, httplib.BadStatusLine, urllib2.URLError)
        self.starturl = url
        options = webdriver.chrome.options.Options()
        options.add_experimental_option('excludeSwitches', ['disable-component-update'])
        options.add_argument("--kiosk")
        options.add_argument("--user-data-dir=%s" % os_join(const.userdatafolder, "chromeprofile"))
        if const.os == "linux":
            driverpath = os_join(const.addonpath, "resources", "chromedriver_linux32", "chromedriver")
        elif const.os == "windows":
            driverpath = os_join(const.addonpath, "resources", "chromedriver_win32", "chromedriver.exe")
        elif const.os == "osx":
            driverpath = os_join(const.addonpath, "resources", "chromedriver_mac32", "chromedriver")
        self.driver = webdriver.Chrome(executable_path=driverpath, chrome_options=options)

        self.driver.get("http://%s" % url)


    def trigger_player(self):
        log.info("triggering player")
        m = PyMouse()
        try:
            try:
                playbutton = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "play-icon")))
                playbutton.click()
                rect = playbutton.location
                size = playbutton.size
            except TimeoutException:
                playerelement = self.driver.find_element_by_id("playerelement")
                playerelement.click()
                rect = playerelement.location
                size = playerelement.size
            player_coord = {"x": int(rect['x']+(size['width']/2)),
                            "y": int(rect['y']+(size['height']/2))}
            log.info(player_coord)
            log.info("waitong for player ready for fullscreen")
            i = 0
            while i < 10:
                player_ready = "ProgressTracker" in self.driver.find_elements_by_tag_name("script")[0].get_attribute('src')
                if player_ready:
                    break
                else:
                    xbmc.sleep(1000)
            else:
                log.info("couldnt find progressbar, don't know if player ready")

            log.info("doube_clicking")
            # playerelement = self.driver.find_element_by_id("playerelement")
            m.move(**player_coord)
            xbmc.sleep(200)
            m.click(n=2, **player_coord)


        except self.seleniumerrors:
            log.info("trigger_player interrupted, browser closed?")
            log.info(traceback.format_exc())

    def gather_urls_wait_for_exit(self):
        log.info("gathering urls")
        self.watched = []
        WatchedEpisode = namedtuple("Watched", "id duration")
        current_nrkid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.starturl)
        startwatch = datetime.now()
        last_stored_url = self.starturl
        try:
            while True:
                if self.driver.current_url == last_stored_url:
                    xbmc.sleep(1000)
                    continue
                last_stored_url = self.driver.current_url
                new_nrkid, is_nrkepisode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.driver.current_url)
                if is_nrkepisode and current_nrkid != new_nrkid:
                    duration = datetime.now() - startwatch
                    self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
                    log.info("watched: %s:" % self.watched)

                    current_nrkid = new_nrkid
                    startwatch = datetime.now()
        except self.seleniumerrors:
            duration = datetime.now() - startwatch
            self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
        log.info("finished gathering urls")
        log.info("watched: %s" % self.watched)

    def focus_player(self):
        self.driver.execute_script("window.focus();")

    def wait_until_closed(self):
        log.info("wait_until_closed")
        try:
            while self.driver.title:
                xbmc.sleep(200)
        except self.seleniumerrors:
            try:
                self.close()
            except self.seleniumerrors:
                pass
        log.info("wait_until_closed finished")



    def close(self):
        self.driver.quit()


class IEbrowser(object):
    def open(self, url):
        self.ie = Dispatch("InternetExplorer.Application")
        self.ie.Visible = 1
        self.ie.FullScreen = 1
        self.starturl = url
        self.handle = self.ie.HWND
        win32gui.SetForegroundWindow(self.handle)
        self.ie.Navigate(self.starturl)

    def trigger_player(self):
        log.info("triggering player")
        m = PyMouse()
        try:
            while self.ie.busy:
                xbmc.sleep(100)
            try:
                playicon = next(elem for elem in self.ie.document.body.all.tags("span") if elem.className == 'play-icon')
                playicon.click()
                log.info("clicked play")
                rect = playicon.getBoundingClientRect()
                player_coord = {"x": rect.left, "y": rect.top}
            except StopIteration:
                log.info("couldn't fint play")
                playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement")
                rect = playerelement.getBoundingClientRect()
                player_coord = {"x": (int(rect.left+rect.right/2)), "y": (int(rect.top+rect.bottom/2))}
                log.info(player_coord)
                m.click(button=1, n=1, **player_coord)

            log.info("waitong for player ready for fullscreen")
            for _ in range(10):
                player_ready = next((elem for elem in self.ie.document.head.all.tags("script") if "ProgressTracker" in elem.getAttribute("src")), False)
                if player_ready:
                    break
                xbmc.sleep(1000)
            else:
                log.info("couldnt find progressbar, don't know if player ready")

            log.info("doube_clicking")
            m.move(**player_coord)
            xbmc.sleep(200)
            m.click(n=2, **player_coord)
            # xbmc.sleep(70)
            # m.click(**player_coord)
        except (pywintypes.com_error, AttributeError):
            log.info("trigger_player interrupted, browser closed?")
            log.info(traceback.format_exc())

    def gather_urls_wait_for_exit(self):
        log.info("gathering urls")
        self.watched = []
        WatchedEpisode = namedtuple("Watched", "id duration")
        current_nrkid = re.sub(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.starturl)
        startwatch = datetime.now()
        last_stored_url = self.starturl
        try:
            while True:
                if self.ie.LocationURL == last_stored_url:
                    xbmc.sleep(1000)
                    continue
                last_stored_url = self.ie.LocationURL
                new_nrkid, is_nrkepisode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.ie.LocationURL)
                if is_nrkepisode and current_nrkid != new_nrkid:
                    duration = datetime.now() - startwatch
                    self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
                    log.info("watched: %s:" % self.watched)

                    current_nrkid = new_nrkid
                    startwatch = datetime.now()

        except (pywintypes.com_error, AttributeError):
            duration = datetime.now() - startwatch
            self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
        log.info("finished gathering urls")
        log.info("watched: %s" % self.watched)

    def focus_player(self):
        win32gui.SetForegroundWindow(self.handle)

    def wait_until_closed(self):
        while True:
            try:
                is_open = next((win for win in Dispatch("Shell.Application").Windows() if win.HWND == self.handle), False)
                if is_open:
                    xbmc.sleep(200)
                else:
                    return
            except (pywintypes.com_error, AttributeError):
                pass

    def close(self):
        self.ie.Quit()


def play(url):
    log.info("setting up playback")
    remote = None
    kodiid = xbmc.getInfoLabel('ListItem.DBID')
    overlay = NowPlayingOverly()
    overlay.set_args(title=xbmc.getInfoLabel('ListItem.Title'), duration=xbmc.getInfoLabel('ListItem.Duration'))
    overlay.show()
    listitem = xbmcgui.ListItem(path=os_join(const.addonpath, "resources", "fakeVid.mp4"))
    xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listitem)
    if settings["browser"] == "Internet Explorer":
        browser = IEbrowser()
    elif settings["browser"] == "Chrome":
        browser = SeleniumDriver()
    if settings["remote"]:
        remote = Remote()
        remote.run(browser=browser)
    log.info("starting playback")
    try:
        browser.open(url)
        browser.trigger_player()
        epdict = gen_epdict(kodiid)

        browser.gather_urls_wait_for_exit()

        log.info("Playback finished, cleaning up")
        mark_watched(epdict, browser.watched)
    except:
        raise
    finally:
        browser.wait_until_closed()
        if remote:
            remote.close()
        overlay.close()
        xbmc.PlayList(xbmc.PLAYLIST_VIDEO).clear()

    log.info("playbackend finished")
