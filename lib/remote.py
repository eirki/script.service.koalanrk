# #! /usr/bin/env python
# # -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from multiprocessing.dummy import Process as Thread
from collections import namedtuple
import xbmc
import xbmcgui

from .PyUserInput.pykeyboard import PyKeyboardEvent, PyKeyboard
from .PyUserInput.pymouse import PyMouse
from . import constants as const
from .utils import os_join
from .xbmcwrappers import (log, dialogs)


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
        xbmc.sleep(1) # why?
        PyKeyboardEvent.run(self)
        dialog.close()

        return self.keycode, self.character

    def tap(self, keycode, character, press_bool):
        """get single key then stop keyboardevent"""
        if press_bool:
            self.keycode = keycode
            self.character = character
            log.info(keycode)
            log.info(character)
            self.stop()

    def stop(self):
        PyKeyboardEvent.stop(self)
        log.info("keygetter stopped")


class RemoteListener(PyKeyboardEvent):
    def __init__(self, funcmap):
        self.funcmap = funcmap
        mapped_codes = self.funcmap.values()
        PyKeyboardEvent.__init__(self, capture_some=mapped_codes)

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
    Button = namedtuple("Button", "name func code char")

    def __init__(self):
        self.mapping = self.load_mapping()

    def load_mapping(self):
        try:
            with open(os_join(const.userdatafolder, "remotemapping.json")) as j:
                stored = json.load(j)
        except IOError:
            stored = {}
        log.info(stored)
        no_keys = {"code": None, "char": None}
        mapping = [
            self.Button(name="Play",    func=self.playpause, **stored.get("Play",    no_keys)),
            self.Button(name="Pause",   func=self.playpause, **stored.get("Pause",   no_keys)),
            self.Button(name="Stop",    func=self.stop,      **stored.get("Stop",    no_keys)),
            self.Button(name="Forward", func=self.forward,   **stored.get("Forward", no_keys)),
            self.Button(name="Rewind",  func=self.rewind,    **stored.get("Rewind",  no_keys)),
        ]
        log.info("mapping: %s" % {button.name: button.char for button in mapping})
        return mapping

    def store_mapping(self, mapping):
        dict_for_storage = {button.name: {'code': button.code, 'char': button.char}
                            for button in mapping if any([button.code, button.char])}
        with open(os_join(const.userdatafolder, "remotemapping.json"), "w") as j:
            json.dump(dict_for_storage, j)

    def configure(self):
        while True:
            optionlist = ["%s: %s" % (button.name, button.char) for button in self.mapping] + ["[Clear]"]
            call = dialogs.select('Select function to edit', optionlist)
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

    def run(self):
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.player = player
        x, y = self.m.screen_size()
        self.corner_coors = {'x': x, 'y': y}
        self.wiggle_coors = {'x': x, 'y': y-10}
        funcmap = {button.code: button.func for button in self.mapping if button.code}
        self.listener = RemoteListener(funcmap)
        self.listener.run()
        missing_keys = [button.name for button in self.mapping if button.code not in funcmap]
        if missing_keys:
            log.info("Note, following actions are not mapped to remote: %s" % missing_keys)

    def playpause(self):
        log.info("Remote: playpause triggered")

        self.m.move(**self.wiggle_coors)
        self.k.tap_key(self.k.space_key)
        self.m.move(**self.corner_coors)

    def forward(self):
        log.info("Remote: forward triggered")
        self.k.tap_key(self.k.right_key)

    def rewind(self):
        log.info("Remote: rewind triggered")
        self.k.tap_key(self.k.left_key)

    def stop(self):
        log.info("Remote: stop triggered")
        xbmc.Player().stop()

    def close(self):
        log.info("Closing remote keylistener")
        self.listener.stop()
        log.info("Remote keylistener closed")
