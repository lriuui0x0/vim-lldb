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

    @pynvim.function('ToggleDebugger')
    def toggle_debugger(self, args):
        self.context.toggle_debugger()

    @pynvim.function('SelectTarget')
    def select_target(self, args):
        self.context.select_target()

    @pynvim.function('Launch')
    def launch(self, args):
        self.context.launch()

    @pynvim.function('StepOver')
    def step_over(self, args):
        self.context.step_over()

    @pynvim.function('StepInto')
    def step_into(self, args):
        self.context.step_into()

    @pynvim.function('StepOut')
    def step_out(self, args):
        self.context.step_out()

    @pynvim.function('Resume')
    def resume(self, args):
        self.context.resume()

    @pynvim.function('Stop')
    def stop(self, args):
        self.context.stop()

    @pynvim.function('Kill')
    def kill(self, args):
        self.context.kill()

    @pynvim.function('ToggleBreakpoint')
    def toggle_breakpoint(self, args):
        self.context.toggle_breakpoint()

    @pynvim.function('StackWindow_GotoFrame')
    def stack_window_goto_frame(self, args):
        self.context.stack_window_goto_frame()

    @pynvim.function('StackWindow_NextThread')
    def stack_window_next_thread(self, args):
        self.context.stack_window_next_thread()

    @pynvim.function('StackWindow_PrevThread')
    def stack_window_prev_thread(self, args):
        self.context.stack_window_prev_thread()

    @pynvim.function('BreakpointWindow_GotoBreakpoint')
    def breakpoint_window_goto_breakpoint(self, args):
        self.context.breakpoint_window_goto_breakpoint()

    @pynvim.function('BreakpointWindow_RemoveBreakpoint')
    def breakpoint_window_remove_breakpoint(self, args):
        self.context.breakpoint_window_remove_breakpoint()

    @pynvim.function('WatchWindow_AddWatch')
    def watch_window_add_watch(self, args):
        self.context.watch_window_add_watch()

    @pynvim.function('WatchWindow_ChangeWatch')
    def watch_window_change_watch(self, args):
        self.context.watch_window_change_watch()

    @pynvim.function('WatchWindow_RemoveWatch')
    def watch_window_remove_watch(self, args):
        self.context.watch_window_remove_watch()

    @pynvim.function('WatchWindow_ExpandWatch')
    def watch_window_expand_watch(self, args):
        self.context.watch_window_expand_watch()

    @pynvim.function('WatchWindow_CollapseWatch')
    def watch_window_collapse_watch(self, args):
        self.context.watch_window_collapse_watch()

    @pynvim.autocmd('BufEnter')
    def buffer_sync(self):
        # NOTE: BufEnter is called on vim startup, initialize here
        self.startup()
        self.context.buffer_sync()

    @pynvim.autocmd('TextChanged')
    def breakpoint_sync_back1(self):
        self.context.breakpoint_sync_back()

    @pynvim.autocmd('TextChangedI')
    def breakpoint_sync_back2(self):
        self.context.breakpoint_sync_back()

    @pynvim.autocmd('TextChangedP')
    def breakpoint_sync_back3(self):
        self.context.breakpoint_sync_back()

    @pynvim.autocmd('VimLeavePre')
    def shutdown(self):
        if self.started:
            self.context.exit_broadcaster.BroadcastEventByType(1)
            self.context.event_loop.join()

    def startup(self):
        if not self.started:
            lldb.SBDebugger.Initialize()
            self.context = Context(self.nvim)
            self.started = True

