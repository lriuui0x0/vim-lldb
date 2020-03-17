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
        if not self.started:
            self.startup()
        main.launch(self.debugger, args[0], args[1], args[2], args[3])

    @pynvim.function('StepOver')
    def step_over(self, args):
        if self.started:
            main.step_over(self.debugger)

    @pynvim.function('StepInto')
    def step_into(self, args):
        if self.started:
            main.step_into(self.debugger)

    @pynvim.function('StepOut')
    def step_out(self, args):
        if self.started:
            main.step_out(self.debugger)

    @pynvim.function('Kill')
    def kill(self, args):
        if self.started:
            main.kill(self.debugger)

    def startup(self):
        self.debugger = main.startup(self.nvim)
        self.started = True

