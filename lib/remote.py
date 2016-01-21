# #! /usr/bin/env python
# # -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from multiprocessing.dummy import Process as Thread
from collections import namedtuple

from .utils import (const, os_join, dialogs, log)
from .PyUserInput.pykeyboard import PyKeyboardEvent, PyKeyboard
from .PyUserInput.pymouse import PyMouse

# to configure:
# remote = Remote(capture=True)
# remote.configure()
# # when playing
# remote = Remote(capture_some=True)
# remote.run()
# if remote:
#     remote.stop()


class Remote(PyKeyboardEvent):
    Button = namedtuple("Button", "name func code char")

    def __init__(self, capture=False, capture_some=False):
        self.mapping = self.load_mapping()
        capture_some = [button.code for button in self.mapping] if capture_some else False
        PyKeyboardEvent.__init__(self, capture=capture, capture_some=capture_some)

    def load_mapping(self):
        try:
            with open(os_join(const.userdatafolder, "remotemapping.json")) as j:
                stored = json.load(j)
        except IOError:
            stored = {}
        no_keys = {"code": None, "char": None}
        mapping = [
            self.Button(name="Play",    func=self.playpause, **stored.get("Play",    no_keys)),
            self.Button(name="Pause",   func=self.playpause, **stored.get("Pause",   no_keys)),
            self.Button(name="Stop",    func=self.close,      **stored.get("Stop",    no_keys)),
            self.Button(name="Forward", func=self.forward,   **stored.get("Forward", no_keys)),
            self.Button(name="Rewind",  func=self.rewind,    **stored.get("Rewind",  no_keys)),
        ]
        return mapping

    def configure(self):
        log.info(self.mapping)
        while True:
            optionlist = ["%s: %s" % (button.name, button.char) for button in self.mapping]
            call = dialogs.select('Select function to edit', optionlist)
            if call == -1:
                break
            selected_button = self.mapping[call]
            newkeycode, newcharacter = self.run_get_single_key(selected_button.name)
            self.mapping[call] = selected_button._replace(code=newkeycode, char=newcharacter)
        self.store_mapping(self.mapping)
        # reopen settings

    def store_mapping(self, mapping):
        dict_for_storage = {button.name: {'code': button.code, 'char': button.char}
                            for button in mapping if any([button.code, button.char])}
        with open(os_join(const.userdatafolder, "remotemapping.json"), "w") as j:
            json.dump(dict_for_storage, j)

    def run_get_single_key(self, buttonname):
        """Exits after one tap"""
        self.k = PyKeyboard()
        self.mode = "keygetter"
        thread = Thread(target=PyKeyboardEvent.run, args=[self])
        thread.start()
        dialogs.ok(heading="Input", line1="Please press intended %s button" % buttonname)
        thread.join()
        return self.keycode, self.character

    def run(self, browser):
        """stays open until stop()"""
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.mode = "remote"
        self.browser = browser
        self.pause_coords = {'x': 1920, 'y': 870}
        self.corner_coors = self.m.screen_size()
        self.funcmap = {button.code: button.func for button in self.mapping if button.code}
        log.info("Note, following actions are not mapped to remote: %s" % [button.name for button in self.mapping if not button.code])
        thread = Thread(target=PyKeyboardEvent.run, args=[self])
        thread.start()

    def tap(self, keycode, character, press_bool):
        if self.mode == "keygetter":
            self._tap_keygetter(keycode, character, press_bool)
        elif self.mode == "remote":
            self._tap_remote(keycode, character, press_bool)

    def _tap_keygetter(self, keycode, character, press_bool):
        """get single key then stop keyboardevent"""
        if press_bool:
            self.keycode = keycode
            self.character = character
            log.info(self.character)
            log.info("keygetter stopped")
            log.info("clsoing dialog")
            self.k.tap_key(self.k.escape_key)
            PyKeyboardEvent.stop(self)

    def _tap_remote(self, keycode, character, press_bool):
        """interrupt mapped keys and trigger corresponding function"""
        if press_bool and keycode in self.funcmap:
            self.funcmap[keycode]()

    def playpause(self):
        # self.m.move(**self.pause_coords)
        # xbmc.sleep(100)
        # self.m.click(button=1, n=2, **self.pause_coords)
        # xbmc.sleep(100)
        # self.m.move(**self.corner_coors)

        self.m.move(**self.corner_coors)
        # self.browser.focus_player()
        self.k.tap_key(self.k.space_key )
        self.m.move(**self.corner_coors)

    def forward(self):
        self.k.tap_key(self.k.right_key)

    def rewind(self):
        self.k.tap_key(self.k.left_key)

    def close(self):
        try:
            self.browser.close()
        except AttributeError:
            log.info("couldn't close browser (aldeady closed?)")
        PyKeyboardEvent.stop(self)
