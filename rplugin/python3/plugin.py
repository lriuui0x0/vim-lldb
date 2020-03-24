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
        self.lazy_start()
        self.context.launch(args[0], args[1], args[2], args[3])

    @pynvim.function('StepOver')
    def step_over(self, args):
        self.lazy_start()
        self.context.step_over()

    @pynvim.function('StepInto')
    def step_into(self, args):
        self.lazy_start()
        self.context.step_into()

    @pynvim.function('StepOut')
    def step_out(self, args):
        self.lazy_start()
        self.context.step_out()

    @pynvim.function('Resume')
    def resume(self, args):
        self.lazy_start()
        self.context.resume()

    @pynvim.function('Stop')
    def stop(self, args):
        self.lazy_start()
        self.context.stop()

    @pynvim.function('Kill')
    def kill(self, args):
        self.lazy_start()
        self.context.kill()

    @pynvim.function('ToggleBreakpoint')
    def toggle_breakpoint(self, args):
        self.lazy_start()
        self.context.toggle_breakpoint()

    @pynvim.autocmd('BufEnter')
    def terminate(self):
        self.lazy_start()
        self.context.sync_all_sign()

    @pynvim.autocmd('VimLeavePre')
    def terminate(self):
        if self.started:
            self.context.event_loop_exit.release()
            self.context.event_loop.join()
            lldb.SBDebugger.Terminate()

    def lazy_start(self):
        if not self.started:
            lldb.SBDebugger.Initialize()
            self.nvim.command('autocmd VimLeavePre * call Terminate()')
            self.context = Context(self.nvim)
            self.started = True

