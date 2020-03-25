import os
import threading
from contextlib import contextmanager
import lldb

# TODO
# Ask Greg:
# resource management (e.g. SBTarget), error handling, Python C++ interface
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

def log(nvim, value):
    nvim.command(f'echomsg {repr(value)}')

def logerr(nvim, value):
    nvim.command(f'echoerr {repr(value)}')

def command(nvim, cmd):
    nvim.command(cmd)

def call(nvim, func, *args):
    return nvim.call(func, *args)

def get_file(nvim, buffer):
    return os.path.abspath(call(nvim, 'bufname', buffer))

@contextmanager
def writing(nvim, window):
    call(nvim, 'setwinvar', window, '&readonly', 0)
    call(nvim, 'setwinvar', window, '&modifiable', 1)
    yield
    call(nvim, 'setwinvar', window, '&readonly', 1)
    call(nvim, 'setwinvar', window, '&modifiable', 0)
    call(nvim, 'setwinvar', window, '&modified', 0)

def check_window_exists(nvim, name):
    window_count = call(nvim, 'winnr', '$')
    for window in range(1, window_count + 1):
        window_name = call(nvim, 'getwinvar', window, 'vim_lldb')
        if window_name == name:
            return window
    return 0

def create_window(nvim, name):
    if not check_window_exists(nvim, name):
        command(nvim, 'vnew')

        window = call(nvim, 'winnr')
        call(nvim, 'setwinvar', window, '&readonly', 1)
        call(nvim, 'setwinvar', window, '&modifiable', 0)
        call(nvim, 'setwinvar', window, '&buftype', 'nofile')
        call(nvim, 'setwinvar', window, '&buflisted', 0)
        call(nvim, 'setwinvar', window, '&number', 0)
        call(nvim, 'setwinvar', window, '&ruler', 0)
        call(nvim, 'setwinvar', window, '&wrap', 0)

        command(nvim, f'file vim-lldb({name})')
        call(nvim, 'setwinvar', window, 'vim_lldb', name)

        command(nvim, 'nnoremap <buffer> <CR> :call GotoFrame(0, 0)<CR>')

        command(nvim, 'wincmd p')

def update_window(nvim, name, data):
    window = check_window_exists(nvim, name)
    if window:
        with writing(nvim, window):
            if name == 'stack':
                buffer = call(nvim, 'winbufnr', window)
                call(nvim, 'deletebufline', buffer, 1, '$')
                line = 1
                for thread_info in data['threads']:
                    for frame_info in thread_info['frames']:
                        if frame_info['debuggable']:
                            frame_line = f'{frame_info["function"]}  ({frame_info["file"]}:{frame_info["line"]})'
                        else:
                            frame_line = f'{frame_info["function"]}  ({frame_info["module"]})'
                        call(nvim, 'setbufline', buffer, line, frame_line)
                        line += 1


def goto_file(nvim, file, line, column):
    window = 0
    test_window = call(nvim, 'winnr')
    if not call(nvim, 'getwinvar', test_window, 'vim_lldb'):
        window = test_window
    else:
        test_window = call(nvim, 'winnr', '#')
        if not call(nvim, 'getwinvar', test_window, 'vim_lldb'):
            window = test_window
        else:
            window_count = call(nvim, 'winnr', '$')
            for test_window in range(1, window_count + 1):
                if not call(nvim, 'getwinvar', test_window, 'vim_lldb'):
                    window = test_window
                    break
    if window:
        command(nvim, f'{window} wincmd w')
    else:
        command(nvim, 'vnew')
        window = call(nvim, 'winnr')

    buffer = 0
    buffer_count = call(nvim, 'bufnr')
    for test_buffer in range(1, buffer_count + 1):
        test_file = get_file(nvim, test_buffer)
        if test_file == file:
            buffer = test_buffer
            break
    if buffer:
        command(nvim, f'buffer {buffer}')
    else:
        edit_file = os.path.relpath(file)
        command(nvim, f'edit {edit_file}')

    call(nvim, 'cursor', line, column)

class Context:
    def __init__(self, nvim):
        self.nvim = nvim
        command(self.nvim, 'highlight vim_lldb_highlight_breakpoint guifg=red')
        call(self.nvim, 'sign_define', 'vim_lldb_sign_breakpoint', { 'text': '●', 'texthl': 'vim_lldb_highlight_breakpoint' })
        command(self.nvim, 'highlight vim_lldb_highlight_cursor guifg=yellow')
        call(self.nvim, 'sign_define', 'vim_lldb_sign_cursor', { 'text': '➨', 'texthl': 'vim_lldb_highlight_cursor' })

        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)
        self.target = None
        self.process_info = None

        self.sign_id = 0
        self.bp_list = []
        self.cursor_list = []

        self.event_loop_exit = threading.Semaphore(value = 0)
        self.event_loop = threading.Thread(target=event_loop, args=(self,))
        self.event_loop.start()

    def launch(self, executable, arguments, working_dir, environments):
        self.target = self.debugger.CreateTargetWithFileAndTargetTriple(executable, 'x86_64-unknown-linux-gnu')

        launch_info = lldb.SBLaunchInfo([])
        launch_info.SetExecutableFile(lldb.SBFileSpec(executable), True)
        launch_info.SetArguments(arguments, True)
        launch_info.SetEnvironmentEntries(environments, True)
        launch_info.SetWorkingDirectory(working_dir)
        launch_info.SetLaunchFlags(lldb.eLaunchFlagStopAtEntry)
        error = lldb.SBError()
        process = self.target.Launch(launch_info, error)
        if error.Success():
            self.process_info = get_process_info(process)
            log(self.nvim, self.process_info)
            create_window(self.nvim, 'stack')
            update_window(self.nvim, 'stack', self.process_info)
        else:
            # TODO: Error reporting
            logerr(self.nvim, error.GetCString())


    def step_over(self):
        process = self.target.GetProcess()
        thread = process.GetSelectedThread();
        error = lldb.SBError()
        thread.StepOver(lldb.eOnlyDuringStepping, error)
        if error.Fail():
            # TODO: Error reporting
            logerr(self.nvim, error.GetCString())

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
        file = get_file(self.nvim, call(self.nvim, 'bufnr'))
        line = call(self.nvim, 'line', '.')

        curr_bp = None
        for bp in self.bp_list:
            if bp['file'] == file and bp['line'] == line:
                curr_bp = bp
                break

        if curr_bp:
            self.bp_list.remove(curr_bp)
        else:
            bp = { 'file': file, 'line': line }
            self.bp_list.append(bp)

        self.sync_sign('vim_lldb_sign_breakpoint', self.bp_list)


    def sync_sign(self, sign_type, sign_list):
        buffer_count = call(self.nvim, 'bufnr')
        for buffer in range(1, buffer_count + 1):
            buffer_curr_sign_list = call(self.nvim, 'sign_getplaced', buffer, { 'group': sign_type })[0]['signs']
            buffer_sign_list = [sign for sign in sign_list if sign['file'] == get_file(self.nvim, buffer)]

            for buffer_curr_sign in buffer_curr_sign_list:
                found = False
                for buffer_sign in buffer_sign_list:
                    if buffer_curr_sign['lnum'] == buffer_sign['line']:
                        found = True
                        break
                if not found:
                    call(self.nvim, 'sign_unplace', sign_type, { 'buffer': buffer, 'id': buffer_curr_sign['id'] })

            for buffer_sign in buffer_sign_list:
                found = False
                for buffer_curr_sign in buffer_curr_sign_list:
                    if buffer_sign['line'] == buffer_curr_sign['lnum']:
                        found = True
                        break
                if not found:
                    self.sign_id += 1
                    call(self.nvim, 'sign_place', self.sign_id, sign_type, sign_type, buffer, { 'lnum': buffer_sign['line'] })

    def sync_all_sign(self):
        self.sync_sign('vim_lldb_sign_breakpoint', self.bp_list)
        self.sync_sign('vim_lldb_sign_cursor', self.cursor_list)

    def goto_frame(self, thread, frame):
        thread_info = self.process_info['threads'][0]
        frame = frame or call(self.nvim, 'line', '.')
        frame_info = thread_info['frames'][frame - 1]
        if frame_info['debuggable']:
            goto_file(self.nvim, frame_info['file'], frame_info['line'])


def event_loop(context):
    def process_state_str(state):
        dictionary = {
            lldb.eStateInvalid: "invalid",
            lldb.eStateUnloaded: "unloaded",
            lldb.eStateConnected: "connected",
            lldb.eStateAttaching: "attaching",
            lldb.eStateLaunching: "launching",
            lldb.eStateStopped: "stopped",
            lldb.eStateRunning: "running",
            lldb.eStateStepping: "stepping",
            lldb.eStateCrashed: "crashed",
            lldb.eStateDetached: "detached",
            lldb.eStateExited: "exited",
            lldb.eStateSuspended: "suspended",
        }
        return dictionary[state]

    try:
        listener = context.debugger.GetListener()
        while True:
            event = lldb.SBEvent()
            if listener.WaitForEvent(1, event):
                if lldb.SBProcess.EventIsProcessEvent(event):
                    event_type = event.GetType();
                    if event_type == lldb.SBProcess.eBroadcastBitStateChanged:
                        process = lldb.SBProcess.GetProcessFromEvent(event)
                        state = lldb.SBProcess.GetStateFromEvent(event)
                        context.nvim.async_call(log, context.nvim, process_state_str(state))

                        if state == lldb.eStateStopped:
                            context.process_info = get_process_info(process)
                            context.nvim.async_call(log, context.nvim, context.process_info)
                            context.nvim.async_call(update_window, context.nvim, 'stack', context.process_info)
                        elif state == lldb.eStateRunning:
                            pass
                        elif state == lldb.eStateExited:
                            pass
    except Exception as e:
        context.nvim.async_call(logerr, context.nvim, e.message)

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
            frame_info['debuggable'] = int(frame.GetFunction().IsValid())
            if frame_info['debuggable']:
                line_entry = frame.GetLineEntry()
                frame_info['file'] = line_entry.GetFileSpec().fullpath or ''
                frame_info['line'] = line_entry.GetLine()
                frame_info['column'] = line_entry.GetColumn()

        stop_reason = thread.GetStopReason() 
        if stop_reason != lldb.eStopReasonNone:
            process_info['stopped_thread_id'] = thread_info['id']
    return process_info

