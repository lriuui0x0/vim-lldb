import os
import threading
import traceback
import inspect
from contextlib import contextmanager
import lldb

# TODO
# Ask Greg: resource management (e.g. SBTarget), error handling (SBError vs IsValid), Python C++ interface
# multiple processes per target?
# passing string (and other elements) through API
# guarantee only one thread may have stop reason?
# does GetThreadID change when some thread dies?
# module.GetFileSpec() vs module.GetPlatformFileSpec()?
# relationship between SBSymbol, SBModule, SBSymbolContext
# differences between all the step functions

# TODO
# Vim long time exit
# Unreliable continue stepping
# Workaround airline?
# Investigate wrong frame information, image lookup --verbose --address <pc>

class View:
    VIM_LLDB_WINDOW_KEY = 'vim_lldb'
    VIM_LLDB_SIGN_BREAKPOINT = 'vim_lldb_sign_breakpoint'
    VIM_LLDB_SIGN_CURSOR = 'vim_lldb_sign_cursor'

    def __init__(self, nvim, tid):
        self.nvim = nvim
        self.tid = tid
        self.log_info(f'main thread id: {self.tid}')

        self.sign_id = 0
        self.command(f'highlight {self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT guifg=red')
        self.call('sign_define', self.VIM_LLDB_SIGN_BREAKPOINT, {'text': '●', 'texthl': f'{self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT'})
        self.command(f'highlight {self.VIM_LLDB_SIGN_CURSOR}_HIGHLIGHT guifg=yellow')
        self.call('sign_define', self.VIM_LLDB_SIGN_CURSOR, {'text': '➨', 'texthl': f'{self.VIM_LLDB_SIGN_CURSOR}_HIGHLIGHT'})

    def thread_guard(self):
        if threading.current_thread().ident == self.tid:
            return True
        else:
            frame_info = inspect.stack()[1]
            function = getattr(View, frame_info.function)
            args_info = inspect.getargvalues(frame_info.frame)
            args = list(map(args_info.locals.get, args_info.args))
            self.nvim.async_call(function, *args)
            return False

    def command(self, cmd):
        if self.thread_guard():
            self.nvim.command(cmd)

    def call(self, func, *args):
        if self.thread_guard():
            return self.nvim.call(func, *args)

    # TODO: Figure out how to post multi-line string as one message
    def to_lines(self, value):
        return [repr(line) for line in value.split('\n')]

    def log_info(self, value):
        if self.thread_guard():
            if type(value) == str:
                for line in self.to_lines(value):
                    self.command(f'echomsg {line}')
            else:
                self.command(f'echomsg {repr(value)}')

    def log_error(self, value):
        # NOTE: echoerr seems to be treated as throwing error
        if self.thread_guard():
            if type(value) == str:
                for line in self.to_lines(value):
                    self.command(f'echohl ErrorMsg')
                    self.command(f'echomsg {line}')
            else:
                self.command(f'echohl ErrorMsg')
                self.command(f'echomsg {repr(value)}')

    def get_window(self):
        if self.thread_guard():
            return self.call('winnr')

    def get_last_window(self):
        if self.thread_guard():
            return self.call('winnr', '#')

    def get_window_count(self):
        if self.thread_guard():
            return self.call('winnr', '$')

    def get_buffer(self):
        if self.thread_guard():
            return self.call('bufnr')

    def get_buffer_count(self):
        if self.thread_guard():
            return self.call('bufnr', '$')

    def get_line(self):
        if self.thread_guard():
            return self.call('line', '.')

    def get_line_count(self):
        if self.thread_guard():
            return self.call('line', '$')

    def get_buffer_file(self, buffer = 0):
        if self.thread_guard():
            buffer = buffer or self.get_buffer()
            return os.path.abspath(self.call('bufname', buffer))

    def sync_signs(self, sign_type, sign_list):
        if self.thread_guard():
            buffer_count = self.get_buffer_count()
            for buffer in range(1, buffer_count + 1):
                buffer_curr_sign_list = self.call('sign_getplaced', buffer, { 'group': sign_type })[0]['signs']
                buffer_sign_list = [sign for sign in sign_list if sign['file'] == self.get_buffer_file(buffer)]

                for buffer_curr_sign in buffer_curr_sign_list:
                    found = False
                    for buffer_sign in buffer_sign_list:
                        if buffer_curr_sign['lnum'] == buffer_sign['line']:
                            found = True
                            break
                    if not found:
                        self.call('sign_unplace', sign_type, { 'buffer': buffer, 'id': buffer_curr_sign['id'] })

                for buffer_sign in buffer_sign_list:
                    found = False
                    for buffer_curr_sign in buffer_curr_sign_list:
                        if buffer_sign['line'] == buffer_curr_sign['lnum']:
                            found = True
                            break
                    if not found:
                        self.sign_id += 1
                        priorities = {self.VIM_LLDB_SIGN_BREAKPOINT: 1000, self.VIM_LLDB_SIGN_CURSOR: 2000}
                        self.call('sign_place', self.sign_id, sign_type, sign_type, buffer,
                             { 'lnum': buffer_sign['line'], 'priority': priorities[sign_type]})

    def goto_file(self, file, line, column):
        if self.thread_guard():
            window = 0
            test_window = self.get_window()
            if not self.call('getwinvar', test_window, self.VIM_LLDB_WINDOW_KEY):
                window = test_window
            else:
                test_window = self.get_last_window()
                if not self.call('getwinvar', test_window, self.VIM_LLDB_WINDOW_KEY):
                    window = test_window
                else:
                    window_count = self.get_window_count()
                    for test_window in range(1, window_count + 1):
                        if not self.call('getwinvar', test_window, self.VIM_LLDB_WINDOW_KEY):
                            window = test_window
                            break
            if window:
                self.command(f'{window} wincmd w')
            else:
                self.command('vnew')
                window = self.get_window()

            buffer = 0
            buffer_count = self.get_buffer()
            for test_buffer in range(1, buffer_count + 1):
                test_file = self.get_buffer_file(test_buffer)
                if test_file == file:
                    buffer = test_buffer
                    break
            if buffer:
                self.command(f'buffer {buffer}')
            else:
                edit_file = os.path.relpath(file)
                self.command(f'edit {edit_file}')

            self.call('cursor', line, column)

    def check_window_exists(self, name):
        if self.thread_guard():
            window_count = self.get_window_count()
            for window in range(1, window_count + 1):
                window_name = self.call('getwinvar', window, self.VIM_LLDB_WINDOW_KEY)
                if window_name == name:
                    return window
            return 0

    def create_window(self, name):
        if self.thread_guard():
            if not self.check_window_exists(name):
                self.command('vnew')

                window = self.get_window()
                self.call('setwinvar', window, '&readonly', 1)
                self.call('setwinvar', window, '&modifiable', 0)
                self.call('setwinvar', window, '&buftype', 'nofile')
                self.call('setwinvar', window, '&buflisted', 0)
                self.call('setwinvar', window, '&number', 0)
                self.call('setwinvar', window, '&ruler', 0)
                self.call('setwinvar', window, '&wrap', 0)

                self.command(f'file vim-lldb({name})')
                self.call('setwinvar', window, self.VIM_LLDB_WINDOW_KEY, name)

                if name == 'stack':
                    self.command('nnoremap <buffer> <CR> :call GotoFrame()<CR>')

                self.command('wincmd p')

    def update_window(self, name, data):
        if self.thread_guard():
            @contextmanager
            def writable(window):
                self.call('setwinvar', window, '&readonly', 0)
                self.call('setwinvar', window, '&modifiable', 1)
                yield
                self.call('setwinvar', window, '&readonly', 1)
                self.call('setwinvar', window, '&modifiable', 0)
                self.call('setwinvar', window, '&modified', 0)

            window = self.check_window_exists(name)
            if window:
                with writable(window):
                    if name == 'stack':
                        buffer = self.call('winbufnr', window)
                        self.call('deletebufline', buffer, 1, '$')
                        line = 1
                        for thread_info in data['threads']:
                            for frame_info in thread_info['frames']:
                                if frame_info['type'] == 'full':
                                    frame_line = f'{frame_info["function"]}  ({frame_info["file"]}:{frame_info["line"]})'
                                else:
                                    frame_line = f'{frame_info["function"]}  ({frame_info["module"]})'
                                self.call('setbufline', buffer, line, frame_line)
                                line += 1

    def destory_window(self, name = ''):
        if self.thread_guard():
            while True:
                window_count = self.get_window_count()
                for window in range(1, window_count + 1):
                    window_name = self.call('getwinvar', window, self.VIM_LLDB_WINDOW_KEY)
                    if window_name and (name == '' or window_name == name):
                        if window_count > 1:
                            self.command(f'{window}quit!')
                        else:
                            self.command(f'enew!')
                        break
                if window_count == 1:
                    break

class Context:
    def __init__(self, nvim):
        self.view = View(nvim, threading.current_thread().ident)

        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)

        self.registered_targets = [{ 'executable': 'test/main',  'arguments': [], 'working_dir': '/', 'environments': [] }]
        self.target = None
        self.process_info = None
        self.process_state = None

        self.bp_list = []
        self.cursor_list = []

        self.event_loop_exit = threading.Semaphore(value = 0)
        self.event_loop = threading.Thread(target=event_loop, args=(self,))
        self.event_loop.start()

    def create_target(self, index):
        # TODO: Delete old target? Preserve breakpoint for the same executable
        executable = self.registered_targets[index]['executable']
        self.target = self.debugger.CreateTargetWithFileAndTargetTriple(executable, 'x86_64-unknown-linux-gnu')

    def launch(self):
        if not self.target:
            self.create_target(0)

        executable = self.registered_targets[0]['executable']
        arguments = self.registered_targets[0]['arguments']
        working_dir = self.registered_targets[0]['working_dir']
        environments = self.registered_targets[0]['environments']

        launch_info = lldb.SBLaunchInfo([])
        launch_info.SetExecutableFile(lldb.SBFileSpec(executable), True)
        launch_info.SetArguments(arguments, True)
        launch_info.SetEnvironmentEntries(environments, True)
        launch_info.SetWorkingDirectory(working_dir)
        launch_info.SetLaunchFlags(0)
        error = lldb.SBError()
        process = self.target.Launch(launch_info, error)
        if error.Success():
            self.process_info = get_process_info(process)
            self.process_state = process_state_str(process.GetState())
            self.view.create_window('stack')
        else:
            # TODO: Error reporting
            self.view.log_error(error.GetCString())

    def step_over(self):
        process = self.target.GetProcess()
        thread = process.GetSelectedThread();
        error = lldb.SBError()
        thread.StepOver(lldb.eOnlyDuringStepping, error)
        if error.Fail():
            # TODO: Error reporting
            self.view.log_error(error.GetCString())

    def step_into(self):
        process = self.target.GetProcess()
        thread = process.GetSelectedThread()
        thread.StepInto()

    def step_out(self):
        process = self.target.GetProcess()
        thread = process.GetSelectedThread()
        thread.StepOut()

    def resume(self):
        process = self.target.GetProcess()
        error = process.Continue()
        if error.Fail():
            # TODO: Error reporting
            pass

    def stop(self):
        process = self.target.GetProcess()
        error = process.Stop()
        if error.Fail():
            # TODO: Error reporting
            pass

    def kill(self):
        process = self.target.GetProcess()
        error = process.Kill()
        if error.Fail():
            # TODO: Error reporting
            pass

    def toggle_breakpoint(self):
        if not self.target:
            self.create_target(0)

        file = self.view.get_buffer_file()
        line = self.view.get_line()

        curr_bp = None
        for bp in self.bp_list:
            if bp['file'] == file and bp['line'] == line:
                curr_bp = bp
                break

        if curr_bp:
            self.bp_list.remove(curr_bp)
            if not self.target.BreakpointDelete(curr_bp['id']):
                # TODO: Error handling
                self.view.log_error('Cannot delete breakpoint')
        else:
            bp = self.target.BreakpointCreateByLocation(file, line)
            if bp.IsValid():
                self.bp_list.append({ 'file': file, 'line': line, 'id': bp.GetID() })
            else:
                # TODO: Error handling
                self.view.log_error('Cannot create breakpoint')

        self.view.sync_signs(self.view.VIM_LLDB_SIGN_BREAKPOINT, self.bp_list)

    def sync_signs(self):
        self.view.sync_signs(self.view.VIM_LLDB_SIGN_BREAKPOINT, self.bp_list)
        self.view.sync_signs(self.view.VIM_LLDB_SIGN_CURSOR, self.cursor_list)

    def goto_frame(self, thread = 0, frame = 0):
        thread_info = self.process_info['threads'][0]
        frame = frame or self.get_line()
        frame_info = thread_info['frames'][frame - 1]
        if frame_info['type'] == 'full':
            self.view.goto_file(frame_info['file'], frame_info['line'], frame_info['column'])

    def update_process_cursor(self):
        self.cursor_list = []
        for thread_info in self.process_info['threads']:
            top_frame = thread_info['frames'][0]
            self.cursor_list.append({ 'file': top_frame['file'], 'line': top_frame['line'], 'id': thread_info['id'] })
        self.view.sync_signs(self.view.VIM_LLDB_SIGN_CURSOR, self.cursor_list)

def event_loop(context):
    try:
        context.view.log_info(f'event thread id: {threading.current_thread().ident}')
        listener = context.debugger.GetListener()
        while True:
            event = lldb.SBEvent()
            if listener.WaitForEvent(1, event):
                if lldb.SBProcess.EventIsProcessEvent(event):
                    event_type = event.GetType();
                    if event_type == lldb.SBProcess.eBroadcastBitStateChanged:
                        process = lldb.SBProcess.GetProcessFromEvent(event)
                        state = lldb.SBProcess.GetStateFromEvent(event)
                        context.process_state = process_state_str(state)

                        if state == lldb.eStateStopped:
                            context.process_info = get_process_info(process)
                            context.view.update_window('stack', context.process_info)
                            context.update_process_cursor()
                        elif state == lldb.eStateRunning:
                            pass
                        elif state == lldb.eStateExited:
                            context.process_info = {'threads': []}
                            context.view.destory_window()
                            context.update_process_cursor()
    except Exception:
        context.view.log_error(traceback.format_exc())

def process_state_str(state):
    dictionary = {
        lldb.eStateInvalid: 'invalid',
        lldb.eStateUnloaded: 'unloaded',
        lldb.eStateConnected: 'connected',
        lldb.eStateAttaching: 'attaching',
        lldb.eStateLaunching: 'launching',
        lldb.eStateStopped: 'stopped',
        lldb.eStateRunning: 'running',
        lldb.eStateStepping: 'stepping',
        lldb.eStateCrashed: 'crashed',
        lldb.eStateDetached: 'detached',
        lldb.eStateExited: 'exited',
        lldb.eStateSuspended: 'suspended',
    }
    return dictionary[state]

def get_process_info(process):
    process_info = {}
    process_info['threads'] = []
    for thread in process:
        thread_info = {}
        process_info['threads'].append(thread_info)

        thread_info['id'] = thread.GetIndexID()
        thread_info['tid'] = thread.GetThreadID()

        thread_info['frames'] = []
        for frame in thread:
            frame_info = {}
            thread_info['frames'].append(frame_info)

            frame_info['module'] = frame.GetModule().GetFileSpec().fullpath or ''
            frame_info['function'] = frame.GetDisplayFunctionName() or ''
            frame_info['type'] = 'full' if frame.GetFunction().IsValid() else 'none'
            if frame_info['type'] == 'full':
                line_entry = frame.GetLineEntry()
                frame_info['file'] = line_entry.GetFileSpec().fullpath or ''
                frame_info['line'] = line_entry.GetLine()
                frame_info['column'] = line_entry.GetColumn()
                if not os.path.isfile(frame_info['file']):
                    frame_info['type'] = 'partial'

        stop_reason = thread.GetStopReason() 
        if stop_reason != lldb.eStopReasonNone:
            process_info['stopped_thread_id'] = thread_info['id']
    return process_info

