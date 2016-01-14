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
from multiprocessing.dummy import Process as Thread
import os

from utils import (settings, log, os_join, uni_join, rpc, const)

# sys.path.extend([os_join(const.addonpath, "lib", "pyHook"),
#                  os_join(const.addonpath, "lib", "win32"),
#                  os_join(const.addonpath, "lib", "win32", "win32"),
#                  os_join(const.addonpath, "lib", "win32", "win32", "lib"),
#                  os_join(const.addonpath, "lib", "win32", "Pythonwin")])
# os.environ["PATH"] += ";%s" % os_join(const.addonpath, "lib", "win32", "pywin32_system32")

from .selenium import webdriver
from .selenium.webdriver.common.keys import Keys
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


def gen_epdict(playingfile):
    playingepcode = 'S%02dE%02d' % (playingfile['season'], playingfile['episode'])
    log.debug(playingepcode)
    tvshowid = playingfile["tvshowid"]
    tvshow_dict = rpc("VideoLibrary.GetEpisodes", tvshowid=tvshowid, properties=[
                      "playcount", "season", "episode", "file", "runtime"])
    epdict = {}
    for episode in tvshow_dict['episodes']:
        epcode = 'S%02dE%02d' % (episode['season'], episode['episode'])
        if epcode >= playingepcode:
            kodiid = episode['episodeid']
            playcount = episode['playcount']
            runtime = episode['runtime']
            with open(episode['file'], 'r') as txt:
                ntflxid = re.sub(r".*www.netflix.com/watch/(\d*).*", r"\1", txt.read())
            epdict[ntflxid] = [epcode, kodiid, playcount, runtime]
    return epdict


def get_netflix_watched(visited_urls):
    watched_netflix = []
    for i, (start, url) in enumerate(visited_urls):
        log.info("Watched url: %s" % url)
        ntflxid, found = re.subn(r".*www.netflix.com/watch/(\d+).*", r"\1", url)
        if found:
            log.info("Extracted ntflxid: %s" % ntflxid)
            end = visited_urls[i-1][0] if watched_netflix else arrow.utcnow()
            duration = end - start
            watched_netflix.append([duration, ntflxid])
            log.info("Duration: %s" % duration.seconds)
    watched_netflix.reverse()
    return watched_netflix


def mark_watched(epdict, watched):
    for watchedduration, ntflxid in watched:
        if ntflxid in epdict:
            epcode, kodiid, playcount, runtime = epdict[ntflxid]
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
    rpc("VideoLibrary.SetEpisodeDetails", episodeid=kodiid, playcount=playcount, lastplayed=now)


class SeleniumDriver(object):
    def __init__(self, browser):
        self.browser = browser

    def start(self, url):
        driverpath = os.path.join(home, "iedriver", "IEDriverServer_Win32_2.48.0")
        os.environ["PATH"] += ";%s" % driverpath
        driver = webdriver.Ie(capabilities={
            "initialBrowserUrl": "http://tv.nrksuper.no/serie/mikke-mus/MSUI33006213/sesong-1/episode-2",
            "ignoreZoomSetting": True,
            "ignoreProtectedModeSettings": True,
            })
        window_size = driver.get_window_size()
        print window_size
        print window_size.keys()
        if not (window_size['width'] == 1920 and window_size['height']) == 1080:
            body = driver.find_element_by_tag_name("body")
            body.send_keys(Keys.F11)

    def gather_urls_wait_for_exit(self):
        return watched

    def wait_for_exit(self):
        pass

    def close(self):
        pass

# class InternetExplorerWebbrowser(object):
    # def __init__(self):
    #     self.ie = Dispatch("InternetExplorer.Application")

    # def open(self, url):
    #     self.ie.Visible = 1      # Make it visible (0 = invisible)
    #     self.ie.FullScreen = 1
    #     self.ie.Navigate(url)

    # def gather_urls_wait_for_exit(self):
    #     watched = []
    #     activeurl = ""
    #     while True:
    #         try:
    #             if self.ie.LocationURL != activeurl:
    #                 activeurl = self.ie.LocationURL
    #                 watched.append([arrow.utcnow(), activeurl])
    #         except (pywintypes.com_error, AttributeError):
    #             break
    #         xbmc.sleep(1000)
    #     return watched

    # # def wait_for_exit(self):
    # #     while True:
    # #         try:
    # #             self.ie.LocationURL
    # #         except (pywintypes.com_error, AttributeError):
    # #             break
    # #         xbmc.sleep(1000)

    # def close(self):
    #     self.ie.Quit()
    #     self.ie = None


class PlaybackSession(object):
    def start(self, url):
        '''
        starting playback:
            get url from arg
            open url in either webrowser.ie or selenium.chrome
            listen for urls in open browser (new thread? which closes when browser closing?)
            load keymapping
            start PyUserInputremote control utility
            listen for keypresses or browser closing
            gen epdict?
        '''
        log.info("playbackstart starting")
        if settings["browser"] == "Chrome":
            browser = ChromeSelenium(url)
        elif settings["browser"] == "Internet Explorer":
            browser = InternetExplorerWebbrowser()
        browser.open(url)
        if settings["remote"]:
            remoteprocess = remote.Remote()
            thread = Thread(target=remoteprocess.run, args=browser)
            thread.start()

        self.epdict = gen_epdict()
        self.watched = browser.gather_urls_wait_for_exit()
        # log.info("playbackstart finished")

    def stop(self):
        # To måter å stoppe på:
        #   remoteprocess får kommandoen stop fra keyboardhook. Den må trigge PlaybackSession.stop()
        #   browser lukkes på en annen måte. Da må remoteprocess.stop() og PlaybackSession.stop()  trigges
        '''
        stopping playback:
            ensure that browser is not open and the kodi is active window
            make list of watched ids with duration
            match list with epdict and mar watched
        '''
        log.info("playbackend starting")
        if self.browser:
            self.browser.close()
        if self.remoteprocess:
            self.remoteprocess.terminate()
        if settings["mark auto-played"]:
            mark_watched(self.epdict, self.watched)
        log.info("playbackend finished")



def play(url):
    listitem = xbmcgui.ListItem(path=os_join(const.addonpath, "resources", "fakeVid.mp4"))
    xbmcplugin.setResolvedUrl(handle=int(sys.argv[1]), succeeded=True, listitem=listitem)
    session = PlaybackSession()
    session.start(url)
    session.stop()
    xbmc.PlayList(xbmc.PLAYLIST_VIDEO).clear()


    #     log.info("playbackstart starting")
    #     self.playingfile = playingfile
    #     self.starttime = arrow.now()
    #     self.remoteprocess = None
    #     if settings["remote"]:
    #         mapping = getremotemapping()
    #         log.info("Launching remote utility")
    #         self.remoteprocess = subprocess.Popen([const.ahkexe, os_join(const.ahkfolder, "remote.ahk"), settings["browser"]]+mapping)
    #     if settings["mark auto-played"] and playingfile["file"].startswith(os_join(const.libpath, "Netflix shows")):
    #         if settings["browser"] == "Internet Explorer":
    #             self.historyfile = os_join(const.userdatafolder, "iehistory %s" % self.starttime.timestamp)
    #             log.info("Launching IE historyfile utility")
    #             self.ieprocess = subprocess.Popen(
    #                 [os_join(const.ahkfolder, "AutoHotkey.exe"), os_join(const.ahkfolder, "save iehistory.ahk"), self.historyfile])
    #         self.epdict = gen_epdict(self.playingfile)
    #         log.info(self.epdict)
    #     log.info("playbackstart finished")

    # def end(self):
    #     ''''''
    #     log.info("playbackend starting")
    #     if self.remoteprocess:
    #         self.remoteprocess.terminate()
    #     if settings["mark auto-played"]:
    #         if settings["browser"] == "Internet Explorer":
    #             log.info("Closing IE historyfile utility")
    #             self.ieprocess.terminate()
    #             self.watched = get_ie_urls(self.historyfile)
    #             if exists(self.historyfile):
    #                 os.remove(self.historyfile)
    #         elif settings["browser"] == "Chrome":
    #             self.watched = get_chrome_urls(self.starttime)
    #         mark_watched(self.epdict, self.watched)
    #     log.info("playbackend finished")


# class MyPlayer(xbmc.Player):
#     def __init__(self):
#         xbmc.Player.__init__(self)
#         self.session = None

#     def onPlayBackStarted(self):
#         playingfile = getplayingvideofile()
#         if playingfile["file"].startswith(uni_join(const.libpath, "Netflix")):
#             self.session = ViewingSession()
#             self.session.start(playingfile)

#     def onPlayBackEnded(self):
#         if self.session:
#             self.session.end()
#             self.session = None

# if const.os == "windows" and (settings["mark auto-played"] or settings["remote"]):
#     player = MyPlayer()
#     xbmc.Monitor().waitForAbort()

