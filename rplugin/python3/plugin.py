import sys
from os import path
sys.path.append(path.dirname(__file__))

import pynvim
import lldb
from context import Context

@pynvim.plugin
class Handler(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.started = False
        self.context = None

    @pynvim.function('Launch')
    def launch(self, args):
        self.startup()
        self.context.launch()

    @pynvim.function('StepOver')
    def step_over(self, args):
        self.startup()
        self.context.step_over()

    @pynvim.function('StepInto')
    def step_into(self, args):
        self.startup()
        self.context.step_into()

    @pynvim.function('StepOut')
    def step_out(self, args):
        self.startup()
        self.context.step_out()

    @pynvim.function('Resume')
    def resume(self, args):
        self.startup()
        self.context.resume()

    @pynvim.function('Stop')
    def stop(self, args):
        self.startup()
        self.context.stop()

    @pynvim.function('Kill')
    def kill(self, args):
        self.startup()
        self.context.kill()

    @pynvim.function('ToggleBreakpoint')
    def toggle_breakpoint(self, args):
        self.startup()
        self.context.toggle_breakpoint()

    @pynvim.function('GotoFrame')
    def goto_frame(self, args):
        self.startup()
        self.context.goto_frame(args[0], args[1])

    @pynvim.autocmd('BufEnter')
    def buffer_sync_sign(self):
        self.startup()
        self.context.sync_all_sign()

    @pynvim.autocmd('VimLeavePre')
    def shutdown(self):
        if self.started:
            lldb.SBDebugger.Terminate()
            self.context.event_loop_exit.release()
            self.context.event_loop.join()

    def startup(self):
        if not self.started:
            lldb.SBDebugger.Initialize()
            self.context = Context(self.nvim)
            self.started = True

