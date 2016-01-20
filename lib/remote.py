#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from collections import defaultdict
from PyUserInput.pykeyboard import PyKeyboardEvent, PyKeyboard
from multiprocessing.dummy import Process as Thread

from utils import (const, os_join, dialogs, log)


class KeypressGetter(PyKeyboardEvent):
    def __init__(self):
        self.k = PyKeyboard()
        PyKeyboardEvent.__init__(self, capture=True)

    def run(self):
        log.info("running keygetter")
        PyKeyboardEvent.run(self)

    def tap(self, keycode, character, press_bool):
        if press_bool:
            self.keycode = keycode
            self.character = character
            log.info(self.character)
            self.stop()
            log.info("keygetter stopped")
            log.info("clsoing dialog")
            self.k.tap_key(self.k.escape_key)


def configure():
    try:
        with open(os_join(const.userdatafolder, "remotemapping.json"), "r") as j:
            remotemapping = json.load(j)
    except IOError:
        remotemapping = {}
    buttonlist = ["Play", "Pause", "Stop", "Forward", "Rewind", "Continue Playing at prompt"]
    log.info(remotemapping)
    log.info(buttonlist)
    while True:
        optionlist = ["%s: %s" % (button, remotemapping.get(button)) for button in buttonlist]
        call = dialogs.select('Select function to edit', optionlist)
        if call == -1:
            break
        button = buttonlist[call]
        keygetter = KeypressGetter()
        thread = Thread(target=keygetter.run)
        thread.start()
        dialogs.ok(heading="Input", line1="Please press intended %s button" % button)
        remotemapping[button] = {'code': keygetter.keycode, 'char': keygetter.character}
    log.info(remotemapping)
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

