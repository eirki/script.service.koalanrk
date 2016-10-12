#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import os as os_module
import xbmc

from lib.constants import *

userdatafolder = os_module.path.join(xbmc.translatePath("special://profile").decode("utf-8"), "addon_data", addonid, "test data")
libpath = os_module.path.join(userdatafolder, "Library")
