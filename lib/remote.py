#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
# import pyHook
import json
import sys
import os
bits = 64 if sys.maxsize > 2**32 else 32
sys.path.extend(["C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\pyHook\\pyHook_%s" % bits,
                 "C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\win32\\pypiwin32_%s" % bits,
                 "C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\win32\\pypiwin32_%s\\win32" % bits,
                 "C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\win32\\pypiwin32_%s\\win32\\lib" % bits,
                 "C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\win32\\pypiwin32_%s\\Pythonwin" % bits])
os.environ["PATH"] += ";C:\\Users\\ebs\\Dropbox\\Programmering\\HTPC\\pyuserinput\\2\\win32\\pypiwin32_%s\\pywin32_system32" % bits

from PyUserInput.pykeyboard import PyKeyboardEvent

from utils import const, os_join, dialogs
import json
from pprint import pprint
from multiprocessing.dummy import Process as Thread
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

def getremotemapping():
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
        self.mapping = {mapping["Play"]["code"]: self.rem_play,
                        mapping["Pause"]["code"]: self.rem_pause,
                        mapping["Stop"]["code"]: self.rem_stop,
                        mapping["Forward"]["code"]: self.rem_forward,
                        mapping["Rewind"]["code"]: self.rem_rewind,
                        mapping["Continue Playing at prompt"]["code"]: self.rem_cont_play
                        }
        PyKeyboardEvent.__init__(self, capture_some=self.mapping.keys())

    def run(self, browser):
        print "running remote"
        PyKeyboardEvent.run(self)
        self.browser = browser

    def tap(self, keycode, character, press_bool):
        if press_bool and keycode in self.mapping:
            self.mapping[keycode]()

    def rem_play(self):
        print "play"

    def rem_pause(self):
        print "pause"

    def rem_stop(self):
        print "stop"
        self.browser.close()
        self.stop()

    def rem_forward(self):
        print "forward"

    def rem_rewind(self):
        print "rewind"

    def rem_cont_play(self):
        print "cont_play"

if __name__ in "__main__":
    remote = Remote()
    thread = Thread(target=remote.run)
    # remote.run()
    thread.start()
    time.sleep(1)
    print "do other stuff now"
    # thread.join()
