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

    @pynvim.function('VimLLDB_SelectTarget')
    def select_target(self, args):
        self.context.select_target(args[0])

    @pynvim.function('VimLLDB_ToggleDebugger')
    def toggle_debugger(self, args):
        self.context.toggle_debugger()

    @pynvim.function('VimLLDB_Launch')
    def launch(self, args):
        self.context.launch()

    @pynvim.function('VimLLDB_StepOver')
    def step_over(self, args):
        self.context.step_over()

    @pynvim.function('VimLLDB_StepInto')
    def step_into(self, args):
        self.context.step_into()

    @pynvim.function('VimLLDB_StepOut')
    def step_out(self, args):
        self.context.step_out()

    @pynvim.function('VimLLDB_Resume')
    def resume(self, args):
        self.context.resume()

    @pynvim.function('VimLLDB_Pause')
    def stop(self, args):
        self.context.pause()

    @pynvim.function('VimLLDB_Kill')
    def kill(self, args):
        self.context.kill()

    @pynvim.function('VimLLDB_ToggleBreakpoint')
    def toggle_breakpoint(self, args):
        self.context.toggle_breakpoint()

    @pynvim.function('VimLLDB_StackWindow_GotoFrame')
    def stack_window_goto_frame(self, args):
        self.context.stack_window_goto_frame()

    @pynvim.function('VimLLDB_StackWindow_NextThread')
    def stack_window_next_thread(self, args):
        self.context.stack_window_next_thread()

    @pynvim.function('VimLLDB_StackWindow_PrevThread')
    def stack_window_prev_thread(self, args):
        self.context.stack_window_prev_thread()

    @pynvim.function('VimLLDB_BreakpointWindow_GotoBreakpoint')
    def breakpoint_window_goto_breakpoint(self, args):
        self.context.breakpoint_window_goto_breakpoint()

    @pynvim.function('VimLLDB_BreakpointWindow_RemoveBreakpoint')
    def breakpoint_window_remove_breakpoint(self, args):
        self.context.breakpoint_window_remove_breakpoint()

    @pynvim.function('VimLLDB_WatchWindow_AddWatch')
    def watch_window_add_watch(self, args):
        self.context.watch_window_add_watch()

    @pynvim.function('VimLLDB_WatchWindow_ChangeWatch')
    def watch_window_change_watch(self, args):
        self.context.watch_window_change_watch()

    @pynvim.function('VimLLDB_WatchWindow_RemoveWatch')
    def watch_window_remove_watch(self, args):
        self.context.watch_window_remove_watch()

    @pynvim.function('VimLLDB_WatchWindow_ExpandWatch')
    def watch_window_expand_watch(self, args):
        self.context.watch_window_expand_watch()

    @pynvim.function('VimLLDB_WatchWindow_CollapseWatch')
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

