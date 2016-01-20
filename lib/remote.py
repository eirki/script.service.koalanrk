#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
# import pyHook
import json
import sys
import os
from collections import defaultdict
from PyUserInput.pykeyboard import PyKeyboardEvent

from utils import const, os_join, dialogs
import json
from pprint import pprint
import time




class RemoteConfig(PyKeyboardEvent):
    def __init__(self):
        PyKeyboardEvent.__init__(self, capture=True)

    def tap(self, keycode, character, press_bool):
        if press_bool:
            self.keycode = keycode
            self.character = character
            print self.character
            self.stop()


def configure_remote():
    try:
        with open(os_join(const.userdatafolder, "remotemapping.json"), "r") as j:
            remotemapping = json.load(j)
    except IOError:
        remotemapping = {}
    buttonlist = ["Play", "Pause", "Stop", "Forward", "Rewind", "Continue Playing at prompt"]
    # while True:
        # optionlist = ["%s: %s" % (button, remotemapping.get(button)) for button in buttonlist]
        # call = dialogs.select('Select function to edit', optionlist)
        # if call == -1:
            # break
    for call, button in enumerate(buttonlist):
        dialogs.ok(heading="Input", line1="Please press intended %s button" % button)
        k = RemoteConfig()
        k.run()
        remotemapping[buttonlist[call]] = {'code': k.keycode, 'char': k.character}
    print remotemapping
    with open(os_join(const.userdatafolder, "remotemapping.json"), "w") as j:
        json.dump(remotemapping, j)

def getmapping():
    try:
        with open(os_join(const.userdatafolder, "remotemapping.json")) as j:
            remotemapping = defaultdict(str, json.load(j))
    except IOError:
        remotemapping = defaultdict(str)
    controls = [remotemapping["Play"], remotemapping["Pause"], remotemapping["Stop"],
                remotemapping["Forward"], remotemapping["Rewind"], remotemapping["Continue Playing at prompt"]]
    return controls


class Remote(PyKeyboardEvent):
    def __init__(self, *args, **kwargs):
        self.mod_keys = {"CAPITAL", "LSHIFT", "LCONTROL", "LWIN", "LMENU", "LCONTROL", "RMENU", "RWIN", "APPS", "RCONTROL", "RSHIFT"}
        try:
            with open(os_join(const.userdatafolder, "remotemapping.json"), "r") as j:
                mapping = json.load(j)
        except IOError:
            mapping = {}
        pprint(mapping)
        self.mapping = {mapping["Play"]["code"]: self.play,
                        mapping["Pause"]["code"]: self.pause,
                        mapping["Stop"]["code"]: self.stop,
                        mapping["Forward"]["code"]: self.forward,
                        mapping["Rewind"]["code"]: self.rewind,
                        mapping["Continue Playing at prompt"]["code"]: self.cont_play
                        }
        PyKeyboardEvent.__init__(self, capture_some=self.mapping.keys())

    def run(self, browser):
        print "running remote"
        PyKeyboardEvent.run(self)
        self.browser = browser

    def tap(self, keycode, character, press_bool):
        if press_bool and keycode in self.mapping:
            self.mapping[keycode]()

    def play(self):
        print "play"

    def pause(self):
        print "pause"

    def forward(self):
        print "forward"

    def rewind(self):
        print "rewind"

    def cont_play(self):
        print "cont_play"

    def stop(self):
        try:
            self.browser.close()
        except AttributeError:
            log.info("couldn't close browser (aldeady closed?)")
        PyKeyboardEvent.stop(self)

