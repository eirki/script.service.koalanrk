from __future__ import unicode_literals
import unittest
import xml.etree.ElementTree as ET
import subprocess
import xbmc

from lib import constants as const
from lib.utils import os_join
from lib import playback
from lib import remote


def read_external_player_config(player):
    playerfilername = "chrome" if player == "Chrome" else "iexplore"
    root = ET.parse(os_join(const.masterprofilefolder, "playercorefactory.xml")).getroot()
    for player in root.findall("./players/player"):
        filename = player.find("filename").text
        args = player.find("args").text.replace('"{1}"', '').split()
        if playerfilername in filename:
            return filename, args
    raise Exception("Could not found player file for %s" % player)


class ChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playerfile, cls.playerargs = read_external_player_config(player="Chrome")

    def setUp(self):
        self.playerargs.append(os_join(const.addonpath, "resources", "Example episode.htm"))
        self.playerprocess = subprocess.Popen([self.playerfile] + self.playerargs)
        self.browser = playback.Chrome()
        self.remote = remote.Remote()
        self.remote.run(browser=self.browser)

    def tearDown(self):
        self.remote.close()
        # try:
        self.playerprocess.terminate()

    def test_connect_close_chrome(self):
        self.browser.connect()
        xbmc.sleep(1000)
        self.browser.close()

    def test_playpause_chrome(self):
        self.browser.connect()
        self.browser.trigger_player()
        xbmc.sleep(10000)
        self.remote.playpause()
        xbmc.sleep(1000)
        self.remote.playpause()
        xbmc.sleep(2000)


class InternetExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playerfile, cls.playerargs = read_external_player_config(player="InternetExplorer")

    def setUp(self):
        self.playerargs.append(os_join(const.addonpath, "resources", "Example episode.htm"))
        self.playerprocess = subprocess.Popen([self.playerfile] + self.playerargs)
        self.browser = playback.InternetExplorer()
        self.remote = remote.Remote()
        self.remote.run(browser=self.browser)

    def tearDown(self):
        self.remote.close()
        self.playerprocess.terminate()

    def test_connect_close_internet_explorer(self):
        self.browser.connect()
        xbmc.sleep(1000)
        self.browser.close()

    def test_playpause_internet_explorer(self):
        self.browser.connect()
        self.browser.trigger_player()
        xbmc.sleep(10000)
        self.remote.playpause()
        xbmc.sleep(1000)
        self.remote.playpause()
        xbmc.sleep(2000)



# class Session(unittest.TestCase):
#     def test_session_trigger_start(self):
#         pass

#     def test_session_trigger_end(self):
#         pass

#     def notice_ie(self):
#         pass

#     def notice_not_ie(self):
#         pass

#     def test_mark_episode_watched(self):
#         pass

# class Remote(unittest.TestCase):
#     def interrup_keypress(self):
#         pass
