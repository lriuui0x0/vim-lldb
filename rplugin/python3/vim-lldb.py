import sys
from os import path
sys.path.append(path.dirname(__file__))

import pynvim
import main

@pynvim.plugin
class Handler(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.started = False
        self.debugger = None

    @pynvim.function('Launch')
    def launch(self, args):
        self.lazy_start()
        main.launch(self.debugger, args[0], args[1], args[2], args[3])

    def lazy_start(self):
        if not self.started:
            self.debugger = main.start(self.nvim)

