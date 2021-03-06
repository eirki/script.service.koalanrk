# #! /usr/bin/env python2
# # -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import json
from multiprocessing.dummy import Process as Thread
from collections import namedtuple
import xbmc
import xbmcgui

from pykeyboard import PyKeyboardEvent

from lib import constants as const
from lib import utils
from lib import kodi


class ConfigurationDialog(xbmcgui.WindowXMLDialog):
    def __new__(cls):
        return super(ConfigurationDialog, cls).__new__(cls, "DialogProgress.xml", const.addonpath)

    def __init__(self):
        super(ConfigurationDialog, self).__init__()

    def set_args(self, buttonname):
        self.buttonname = buttonname

    def onInit(self):
        self.getControl(1).setLabel("Input")
        self.getControl(3).setLabel("Please press intended %s button" % self.buttonname)

    def close(self):
        del self


class ConfigurationListener(PyKeyboardEvent):
    def __init__(self):
        PyKeyboardEvent.__init__(self, capture=True)

    def get(self, buttonname):
        """Exits after one tap"""
        dialog = ConfigurationDialog()
        dialog.set_args(buttonname)
        dialog.show()
        xbmc.sleep(1)  # why?
        PyKeyboardEvent.run(self)
        dialog.close()

        return self.keycode, self.character

    def tap(self, keycode, character, press_bool):
        """get single key then stop keyboardevent"""
        if press_bool:
            self.keycode = keycode
            self.character = character
            kodi.log(keycode)
            kodi.log(character)
            self.stop()

    def stop(self):
        PyKeyboardEvent.stop(self)
        kodi.log("keygetter stopped")


class PlaybackListener(PyKeyboardEvent):
    def __init__(self, funcmap):
        self.funcmap = funcmap
        mapped_codes = set(self.funcmap)
        PyKeyboardEvent.__init__(self, capture_codes=mapped_codes)

    def run(self):
        """stays open until stop()"""
        thread = Thread(target=PyKeyboardEvent.run, args=[self])
        thread.start()

    def tap(self, keycode, character, press_bool):
        """interrupt mapped keys and trigger corresponding function"""
        if press_bool and keycode in self.funcmap:
            self.funcmap[keycode]()

    def stop(self):
        PyKeyboardEvent.stop(self)


class Remote(object):
    Button = namedtuple('Button', ['name', 'func', 'code', 'char'])

    def __init__(self):
        self.mapping = self.load_mapping()

    def load_mapping(self):
        try:
            with open(utils.os_join(const.userdatafolder, "remotemapping.json")) as j:
                stored = json.load(j)
        except IOError:
            stored = {}
        no_keys = {"code": None, "char": None}
        mapping = [
            self.Button(name="Play",    func=self.playpause, **stored.get("Play",    no_keys)),
            self.Button(name="Pause",   func=self.playpause, **stored.get("Pause",   no_keys)),
            self.Button(name="Stop",    func=self.stop,      **stored.get("Stop",    no_keys)),
            self.Button(name="Forward", func=self.forward,   **stored.get("Forward", no_keys)),
            self.Button(name="Rewind",  func=self.rewind,    **stored.get("Rewind",  no_keys)),
            self.Button(name="Enter fullscreen",  func=self.enter_fullscreen,
                        **stored.get("Enter fullscreen",  no_keys)),
        ]
        return mapping

    def store_mapping(self, mapping):
        dict_for_storage = {button.name: {'code': button.code, 'char': button.char}
                            for button in mapping if any([button.code, button.char])}
        with open(utils.os_join(const.userdatafolder, "remotemapping.json"), "w") as j:
            json.dump(dict_for_storage, j)

    def configure(self):
        while True:
            optionlist = ["%s: %s" % (button.name, button.char) for button in self.mapping] + ["[Clear]"]
            call = kodi.Dialog.select('Select function to edit', optionlist)
            if call == -1:
                break
            elif optionlist[call] == "[Clear]":
                self.mapping = [button._replace(code=None, char=None) for button in self.mapping]
            else:
                selected_button = self.mapping[call]
                listener = ConfigurationListener()
                newkeycode, newcharacter = listener.get(selected_button.name)
                self.mapping[call] = selected_button._replace(code=newkeycode, char=newcharacter)
        self.store_mapping(self.mapping)

    def run(self, player):
        self.player = player
        funcmap = {button.code: button.func for button in self.mapping if button.code}
        self.listener = PlaybackListener(funcmap)
        self.listener.run()
        missing_keys = [button.name for button in self.mapping if button.code not in funcmap]
        if missing_keys:
            kodi.log("Note, following actions are not mapped to remote: %s" % missing_keys)

    def close(self):
        self.listener.stop()
        kodi.log("Remote keylistener closed")

    def playpause(self):
        kodi.log("Remote: playpause triggered")
        self.player.playpause()

    def forward(self):
        kodi.log("Remote: forward triggered")
        self.player.forward()

    def rewind(self):
        kodi.log("Remote: rewind triggered")
        self.player.rewind()

    def enter_fullscreen(self):
        kodi.log("Remote: enter fullscreen triggered")
        self.player.enter_fullscreen()

    def stop(self):
        kodi.log("Remote: stop triggered")
        self.player.stop()
