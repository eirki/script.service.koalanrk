# coding: utf-8
from __future__ import unicode_literals
import unittest
from bs4 import BeautifulSoup
import re

from lib import constants as const
from lib import utils
import main


def read_settings_xml(player):
    soup = BeautifulSoup(utils.os_join(const.masterprofilefolder, "playercorefactory.xml")).getroot()
    for action in soup.find_all("setting", type="action"):
        script, mode, action = re.match(r"RunScript\(([\w\.]*), mode=(\w*), action=(\w*).*", action["action"]).groups()
        print script
        print mode
        print action
    raise Exception("Could not found player file for %s" % player)

