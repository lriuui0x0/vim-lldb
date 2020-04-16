# NOTE: Vim runtime cannot load local .py package by default for some reason, we have to manually manipulate the loading path
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

    @pynvim.function('VimLLDB_OutputWindow_NextStream')
    def output_window_next_stream(self, args):
        self.context.output_window_next_stream()

    @pynvim.function('VimLLDB_OutputWindow_PrevStream')
    def output_window_prev_stream(self, args):
        self.context.output_window_prev_stream()

    @pynvim.autocmd('BufEnter')
    def buffer_sync(self):
        # NOTE: BufEnter is called on vim startup, initialize here instead of VimEnter because VimEnter is called after all buffers are loaded
        self.startup()
        # NOTE: When a new buffer enters, we should display the signs and lock the files correctly.
        self.context.buffer_sync()

    # NOTE: When text is changed, the sign positions might change. We need to sync this back with current breakpoint list
    @pynvim.autocmd('TextChanged')
    @pynvim.autocmd('TextChangedI')
    @pynvim.autocmd('TextChangedP')
    def buffer_sync_back(self):
        # NOTE: In some cases TextChanged can be triggered before (or concurrently?) with BufEnter, so we call startup here as well
        self.startup()
        # NOTE: When text changes, the sign positions may change and we need to get that information back into our in-memory object representation
        self.context.buffer_sync_back()

    @pynvim.autocmd('VimLeavePre')
    def shutdown(self):
        if self.started:
            # NOTE: Shutdown the event loop by sending it an event for it to break out, so that all threads are cleared when vim exits hence vim doesn't hang
            self.context.exit_broadcaster.BroadcastEventByType(1)
            self.context.event_loop.join()

    def startup(self):
        if not self.started:
            lldb.SBDebugger.Initialize()
            self.context = Context(self.nvim)
            self.started = True

