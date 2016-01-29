#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
import re
import xbmc
from datetime import (timedelta, datetime)
import sys
import xbmcgui
import xbmcplugin
from collections import namedtuple

from lib.selenium import webdriver
from lib.selenium.webdriver.common.keys import Keys
from lib.selenium.webdriver.common.by import By
from lib.selenium.webdriver.support.ui import WebDriverWait
from lib.selenium.webdriver.support import expected_conditions as EC
from lib.selenium.common.exceptions import TimeoutException
from lib.selenium.webdriver.common.action_chains import ActionChains
from lib import selenium

from win32com.client import Dispatch
import pywintypes
import win32gui

from lib.PyUserInput.pymouse import PyMouse
from lib.utils import (settings, log, os_join, uni_join, rpc, const)
from lib.remote import Remote


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
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    rpc("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


class SeleniumDriver(object):

    def open(self, url):
        options = selenium.webdriver.chrome.options.Options()
        options.add_experimental_option('excludeSwitches', ['disable-component-update'])
        options.add_argument('--kiosk')
        options.add_argument("--profile-directory=Eirik")
        d = "C:/Users/Eirki/AppData/Local/Google/Chrome/User Data/Default"
        options.add_argument("--user-data-dir=%s" % d)
        self.driver = webdriver.Chrome("D:/Dropbox/Programmering/HTPC/selenium/chromedriver.exe", chrome_options=options)

        self.driver.get(url)

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
        startwatch = datetime.now()
        last_stored_url = self.driver.current_url

        WatchedEpisode = namedtuple("Watched", "id duration")
        log.info("gathering urls")
        while True:
            try:
                if self.driver.current_url != last_stored_url:
                    new_nrkid, is_newepisode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.driver.current_url)
                    if is_newepisode and current_nrkid != new_nrkid:
                        duration = datetime.now() - startwatch
                        self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))

                        current_nrkid = new_nrkid
                        startwatch = datetime.now()
                    last_stored_url = self.driver.current_url
                    log.info("watched: %s:" % self.watched)
            except (selenium.common.exceptions.WebDriverException, AttributeError):
                duration = datetime.now() - startwatch
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


class IEbrowser(object):
    def open(self, url):
        self.ie = Dispatch("InternetExplorer.Application")
        self.ie.Visible = 1
        self.ie.FullScreen = 1
        self.ie.Navigate(url)
        win32gui.SetForegroundWindow(self.ie.HWND)

    def trigger_player(self):
        log.info("triggering player")
        m = PyMouse()
        while self.ie.busy:
            xbmc.sleep(100)
        try:
            playicon = next(elem for elem in self.ie.document.body.all.tags("span") if elem.className == 'play-icon')
            playicon.click()
            log.info("clicked play")
            rect =  playicon.getBoundingClientRect()
            player_coord = {"x": rect.left, "y": rect.top}
        except StopIteration:
            log.info("couldn't fint play")
            playerelement = next(elem for elem in self.ie.document.body.all.tags("div") if elem.id == "playerelement")
            rect =  playerelement.getBoundingClientRect()
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
        xbmc.sleep(100)
        m.click(button=1, n=2, **player_coord)

    def focus_player(self):
        win32gui.SetForegroundWindow(self.ie.HWND)

    def gather_urls_wait_for_exit(self):
        log.info("setting up url gathering")
        self.watched = []
        found = False
        while not found:
            current_nrkid, found = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.ie.LocationURL)
            xbmc.sleep(1000)
        startwatch = arrow.now()
        last_stored_url = self.ie.LocationURL

        WatchedEpisode = namedtuple("Watched", "id duration")
        log.info("gathering urls")
        while True:
            try:
                if self.ie.LocationURL != last_stored_url:
                    new_nrkid, is_newepisode = re.subn(r'.*tv.nrk(?:super)?.no/serie/.*?/(.*?)/.*', r"\1", self.ie.LocationURL)
                    if is_newepisode and current_nrkid != new_nrkid:
                        duration = arrow.now() - startwatch
                        self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))

                        current_nrkid = new_nrkid
                        startwatch = arrow.now()
                    last_stored_url = self.ie.LocationURL
                    log.info("watched: %s:" % self.watched)
            except (pywintypes.com_error, AttributeError):
                duration = arrow.now() - startwatch
                self.watched.append(WatchedEpisode(id=current_nrkid, duration=duration))
                break
            xbmc.sleep(1000)
        log.info("finished gathering urls")
        log.info("watched: %s" % self.watched)

    def close(self):
        self.ie.Quit()


def player_wrapper(play_func):
    def wrapper(*args):
        xbmc.executebuiltin("ActivateWindow(busydialog)")
        listitem = xbmcgui.ListItem(path=os_join(const.addonpath, "resources", "fakeVid.mp4"))
        xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listitem)
        try:
            play_func(*args)
        except:
            raise
        finally:
            xbmc.PlayList(xbmc.PLAYLIST_VIDEO).clear()
            xbmc.executebuiltin("Dialog.Close(busydialog)")
    return wrapper


@player_wrapper
def play(url):
    log.info("playbackstart starting")
    if settings["browser"] == "Internet Explorer":
        browser = IEbrowser()
    elif settings["browser"] == "Chrome":
        browser = SeleniumDriver()
    if settings["remote"]:
        log.info("Launching remote utility")
        remote = Remote()
        remote.run(browser)
    browser.open(url)
    browser.trigger_player()
    kodiid = xbmc.getInfoLabel('ListItem.DBID')
    epdict = gen_epdict(kodiid)
    log.info("playbackstart finished")

    browser.gather_urls_wait_for_exit()

    log.info("playbackend starting")
    log.info(browser.watched)
    try:
        browser.close()
    except (AttributeError, pywintypes.com_error):
        log.info("playback could not close browser. already closed?")
    try:
        remote.stop()
    except AttributeError:
        log.info("playback could not close remote. already closed?")
    except NameError:
        log.info("remote not activated")
    mark_watched(epdict, browser.watched)
    log.info("playbackend finished")
