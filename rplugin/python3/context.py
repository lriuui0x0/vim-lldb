import os
import re
import threading
import traceback
import inspect
from contextlib import contextmanager
import lldb

# TODO
# Ask Greg:
# resource management (e.g. SBTarget), error handling (SBError vs IsValid), Python C++ interface
# multiple processes per target?
# passing string (and other elements) through API
# guarantee only one thread may have stop reason?
# does GetThreadID change when some thread dies?
# module.GetFileSpec() vs module.GetPlatformFileSpec()?
# relationship between SBSymbol, SBModule, SBSymbolContext
# differences between all the step functions
# Why does StepInto not fail

# TODO
# Investigate wrong frame information, image lookup --verbose --address <pc>

class Context:
    VIM_LLDB_WINDOW_KEY = 'vim_lldb'
    VIM_LLDB_WINDOW_LOCK = 'vim_lldb_window_lock'
    VIM_LLDB_SIGN_BREAKPOINT = 'vim_lldb_sign_breakpoint'
    VIM_LLDB_SIGN_CURSOR = 'vim_lldb_sign_cursor'
    EXITED_PROCESS_INFO = { 'state': 'exited', 'threads': [] }

    def __init__(self, nvim):
        self.nvim = nvim
        self.tid = threading.current_thread().ident
        self.log_info(f'main thread id: {self.tid}')

        self.sign_id = 0
        self.command(f'highlight {self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT guifg=red')
        self.call('sign_define', self.VIM_LLDB_SIGN_BREAKPOINT, {'text': '●', 'texthl': f'{self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT'})
        self.command(f'highlight {self.VIM_LLDB_SIGN_CURSOR}_HIGHLIGHT guifg=yellow')
        self.call('sign_define', self.VIM_LLDB_SIGN_CURSOR, {'text': '➨', 'texthl': f'{self.VIM_LLDB_SIGN_CURSOR}_HIGHLIGHT'})

        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)

        self.targets = []
        self.selected_target = None
        self.select_target(0)

        self.process_info = self.EXITED_PROCESS_INFO
        self.selected_thread_info = None
        self.selected_frame_info_list = []
        self.breakpoint_list = []
        self.watch_list = []

        self.exit_broadcaster = lldb.SBBroadcaster('exit_broadcaster')
        self.event_loop = threading.Thread(target=event_loop, args=(self,))
        self.event_loop.start()

    def command(self, cmd):
        self.nvim.command(cmd)

    def call(self, func, *args):
        return self.nvim.call(func, *args)

    def to_lines(self, value):
        return [repr(line) for line in value.split('\n')]

    def thread_guard(self):
        if threading.current_thread().ident == self.tid:
            return True
        else:
            frame_info = inspect.stack()[1]
            function = getattr(Context, frame_info.function)
            args_info = inspect.getargvalues(frame_info.frame)
            args = list(map(args_info.locals.get, args_info.args))
            self.nvim.async_call(function, *args)
            return False

    def log_info(self, value):
        if self.thread_guard():
            if type(value) == str:
                for line in self.to_lines(value):
                    self.command(f'echomsg {line}')
            else:
                self.command(f'echomsg {repr(value)}')

    def log_error(self, value):
        if self.thread_guard():
            if type(value) == str:
                for line in self.to_lines(value):
                    # NOTE: echoerr seems to be treated as throwing error
                    self.command(f'echohl ErrorMsg')
                    self.command(f'echomsg {line}')
                    self.command(f'echohl NormalNC')
            else:
                self.command(f'echohl ErrorMsg')
                self.command(f'echomsg {repr(value)}')
                self.command(f'echohl NormalNC')

    def get_window(self):
        return self.call('winnr')

    def get_last_window(self):
        return self.call('winnr', '#')

    def get_window_count(self):
        return self.call('winnr', '$')

    def get_buffer(self):
        return self.call('bufnr')

    def get_buffer_count(self):
        return self.call('bufnr', '$')

    def is_buffer_valid(self, buffer):
        return bool(self.call('buflisted', buffer))

    def get_window_buffer(self, window = 0):
        return self.call('winbufnr', window)

    def get_line(self):
        return self.call('line', '.')

    def get_line_count(self):
        return self.call('line', '$')

    def get_buffer_file(self, buffer = 0):
        buffer = buffer or self.get_buffer()
        return os.path.abspath(self.call('bufname', buffer))

    def sync_signs(self, sign_type, sign_list):
        buffer_count = self.get_buffer_count()
        for buffer in range(1, buffer_count + 1):
            if self.is_buffer_valid(buffer):
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

    def sync_back_signs(self, sign_type, sign_list):
        buffer = self.get_buffer()
        buffer_curr_sign_list = sorted(self.call('sign_getplaced', buffer, { 'group': sign_type })[0]['signs'], key=lambda x: x['lnum'])
        buffer_sign_list = sorted([sign for sign in sign_list if sign['file'] == self.get_buffer_file(buffer)], key=lambda x: x['line'])

        has_change = False
        for i in range(len(buffer_sign_list)):
            if buffer_sign_list[i]['line'] != buffer_curr_sign_list[i]['lnum']:
                buffer_sign_list[i]['line'] = buffer_curr_sign_list[i]['lnum']
                has_change = True

        return has_change

    def goto_file(self, file, line, column):
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
            if self.is_buffer_valid(test_buffer):
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

    def is_window(self, name = ''):
        window = self.get_window()
        window_name = self.call('getwinvar', window, self.VIM_LLDB_WINDOW_KEY)
        return window_name and (name == '' or window_name == name)

    def check_window_exists(self, name = ''):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            window_name = self.call('getwinvar', window, self.VIM_LLDB_WINDOW_KEY)
            if window_name:
                if name == '' or window_name == name:
                    return window
        return 0

    def create_window(self, name):
        window = self.get_window()
        self.call('setwinvar', window, '&readonly', 1)
        self.call('setwinvar', window, '&modifiable', 0)
        self.call('setwinvar', window, '&buftype', 'nofile')
        self.call('setwinvar', window, '&buflisted', 0)
        self.call('setwinvar', window, '&bufhidden', 'wipe')
        self.call('setwinvar', window, '&number', 0)
        self.call('setwinvar', window, '&ruler', 0)
        self.call('setwinvar', window, '&wrap', 0)

        self.command(f'file vim-lldb({name})')
        self.call('setwinvar', window, self.VIM_LLDB_WINDOW_KEY, name)

        if name == 'stack':
            self.command('nnoremap <buffer> <CR> :call StackWindow_GotoFrame()<CR>')
        elif name == 'breakpoint':
            self.command('nnoremap <buffer> <CR> :call BreakpointWindow_GotoBreakpoint()<CR>')
            self.command('nnoremap <buffer> <DEL> :call BreakpointWindow_RemoveBreakpoint()<CR>')
        elif name == 'watch':
            self.command('nnoremap <buffer> ma :call WatchWindow_AddWatch()<CR>')
            self.command('nnoremap <buffer> mm :call WatchWindow_ChangeWatch()<CR>')
            self.command('nnoremap <buffer> md :call WatchWindow_RemoveWatch()<CR>')

    def destory_window(self, name = ''):
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

    def update_window(self, name):
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
                buffer = self.call('winbufnr', window)
                self.call('deletebufline', buffer, 1, '$')
                if name == 'stack':
                    if self.process_info['state'] == 'exited':
                        self.call('setbufline', buffer, 1, 'processs exited')
                    else:
                        selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
                        selected_frame_info = self.selected_frame_info_list[selected_thread_index]
                        for line, frame_info in enumerate(self.selected_thread_info['frames'], start=1):
                            if frame_info['type'] == 'full':
                                frame_line = f'{"*" if frame_info == selected_frame_info else " "} {frame_info["function"]}  ({frame_info["file"]}:{frame_info["line"]})'
                            else:
                                frame_line = f'  {frame_info["function"]}  ({frame_info["module"]})'
                            self.call('setbufline', buffer, line, frame_line)
                        self.call('setbufline', buffer, len(self.selected_thread_info['frames']) + 1, '')
                        self.call('setbufline', buffer, len(self.selected_thread_info['frames']) + 2, f'thread {self.selected_thread_info["id"]}')
                elif name == 'breakpoint':
                    for line, breakpoint in enumerate(self.breakpoint_list, start=1):
                        self.call('setbufline', buffer, line, f'{breakpoint["file"]}:{breakpoint["line"]}')
                elif name == 'watch':
                    for line, watch in enumerate(self.watch_list, start=1):
                        if self.process_info['state'] == 'exited':
                            self.call('setbufline', buffer, line, f'{watch}')
                        else:
                            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
                            selected_frame_info = self.selected_frame_info_list[selected_thread_index]
                            if selected_frame_info and selected_frame_info['type'] == 'full':
                                frame = selected_frame_info['handle']
                                value = frame.EvaluateExpression(watch)
                                self.call('setbufline', buffer, line, f'{watch}  {value.GetValue()}')
                            else:
                                self.call('setbufline', buffer, line, f'{watch}')

    def lock_files(self):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            buffer = self.get_window_buffer()
            if re.compile(r'.*\.(c|cpp|cxx|h|hpp|hxx)$').match(self.get_buffer_file(buffer)):
                self.call('setwinvar', window, '&readonly', 1)
                self.call('setwinvar', window, '&modifiable', 0)
                self.call('setwinvar', window, self.VIM_LLDB_WINDOW_LOCK, 1)

    def unlock_files(self):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            if self.call('getwinvar', window, self.VIM_LLDB_WINDOW_LOCK):
                self.call('setwinvar', window, '&readonly', 0)
                self.call('setwinvar', window, '&modifiable', 1)
                
    def toggle_debugger(self):
        window = self.get_window()

        if self.check_window_exists():
            self.destory_window()
        else:
            window = self.get_window()

            self.command('vnew')
            self.create_window('breakpoint')

            self.command('new')
            self.create_window('stack')

            self.command('new')
            self.create_window('watch')

            self.command(f'{window} wincmd w')

            self.update_window('stack')
            self.update_window('breakpoint')
            self.update_window('watch')

    def select_target(self, selection = 0):
        if self.call('exists', 'g:vim_lldb_targets'):
            targets = self.call('eval', 'g:vim_lldb_targets')
        else:
            self.log_error('No target definition')
            return False
        self.targets = []
        if type(targets) == list:
            for target in targets:
                if (type(target) == dict and set(target) == {'name', 'executable', 'arguments', 'working_dir', 'environments'}):
                    self.targets.append(target)
                else:
                    self.log_error('Incorrect target format')
                    return False

        self.selected_target = None
        if type(selection) == int:
            if selection >= 0 and selection < len(self.targets):
                self.selected_target = self.targets[selection].copy()
            else:
                self.log_error('Target index out of bound')
                return False
        elif type(selection) == str:
            matched_targets = [target for target in self.targets if target.name == selection]
            if len(matched_targets) == 1:
                self.selected_target = matched_targets.copy()
            else:
                self.log_error('Target name not found' if len(matched_targets) == 0 else 'Ambiguous target name')
                return False
        else:
            self.log_error('Invalid target selection')
            return False

        return True

    def launch(self):
        if self.selected_target:
            if self.process_info['state'] == 'exited':
                executable = self.selected_target['executable']
                arguments = self.selected_target['arguments']
                working_dir = self.selected_target['working_dir']
                environments = self.selected_target['environments']

                if 'handle' in self.selected_target and self.selected_target['handle']:
                    self.debugger.DeleteTarget(self.selected_target['handle'])
                self.selected_target['handle'] = self.debugger.CreateTargetWithFileAndTargetTriple(executable, 'x86_64-unknown-linux-gnu')

                for breakpoint in self.breakpoint_list:
                    target_breakpoint = self.selected_target['handle'].BreakpointCreateByLocation(breakpoint['file'], breakpoint['line'])
                    if target_breakpoint.IsValid():
                        breakpoint['id'] = target_breakpoint.GetID()
                    else:
                        self.log_error('Cannot create breakpoint')

                launch_info = lldb.SBLaunchInfo([])
                launch_info.SetExecutableFile(lldb.SBFileSpec(executable), True)
                launch_info.SetArguments(arguments, True)
                launch_info.SetEnvironmentEntries(environments, True)
                launch_info.SetWorkingDirectory(working_dir)
                launch_info.SetLaunchFlags(0)
                error = lldb.SBError()
                process = self.selected_target['handle'].Launch(launch_info, error)
                if error.Success():
                    self.lock_files()
                else:
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot launch process from non-exited state')
        else:
            self.log_error('No target selected')

    def step_over(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                process = self.selected_target['handle'].GetProcess()
                thread = process.GetThreadByIndexID(self.selected_thread_info['id']);
                error = lldb.SBError()
                thread.StepOver(lldb.eOnlyDuringStepping, error)
                if error.Fail():
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot step from non-stopped state')
        else:
            self.log_error('No target selected')

    def step_into(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                process = self.selected_target['handle'].GetProcess()
                thread = process.GetThreadByIndexID(self.selected_thread_info['id']);
                thread.StepInto()
            else:
                self.log_error('Cannot step from non-stopped state')
        else:
            self.log_error('No target selected')

    def step_out(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                process = self.selected_target['handle'].GetProcess()
                thread = process.GetThreadByIndexID(self.selected_thread_info['id']);
                thread.StepOut()
            else:
                self.log_error('Cannot step from non-stopped state')
        else:
            self.log_error('No target selected')

    def resume(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                process = self.selected_target['handle'].GetProcess()
                error = process.Continue()
                if error.Fail():
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot resume from non-stopped state')
        else:
            self.log_error('No target selected')

    def stop(self):
        if self.selected_target:
            if self.process_info['state'] == 'running':
                process = self.selected_target['handle'].GetProcess()
                error = process.Stop()
                if error.Fail():
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot stop from non-running state')
        else:
            self.log_error('No target selected')

    def kill(self):
        if self.selected_target:
            if self.process_info['state'] != 'exited':
                process = self.selected_target['handle'].GetProcess()
                error = process.Kill()
                if error.Fail():
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot kill from exited state')
        else:
            self.log_error('No target selected')

    def update_process_cursor(self):
        cursor_list = []
        for thread_info in self.process_info['threads']:
            top_frame = thread_info['frames'][0]
            cursor_list.append({ 'file': top_frame['file'], 'line': top_frame['line'], 'id': thread_info['id'] })
        self.sync_signs(self.VIM_LLDB_SIGN_CURSOR, cursor_list)

    def toggle_breakpoint(self):
        if self.selected_target:
            file = self.get_buffer_file()
            line = self.get_line()

            curr_breakpoint = None
            for breakpoint in self.breakpoint_list:
                if breakpoint['file'] == file and breakpoint['line'] == line:
                    curr_breakpoint = breakpoint
                    break

            if curr_breakpoint:
                if self.process_info['state'] == 'exited':
                    self.breakpoint_list.remove(curr_breakpoint)
                else:
                    if self.selected_target['handle'].BreakpointDelete(curr_breakpoint['id']):
                        self.breakpoint_list.remove(curr_breakpoint)
                    else:
                        self.log_error('Cannot remove breakpoint')
            else:
                if self.process_info['state'] == 'exited':
                    self.breakpoint_list.append({ 'file': file, 'line': line })
                else:
                    breakpoint = self.selected_target['handle'].BreakpointCreateByLocation(file, line)
                    if breakpoint.IsValid():
                        self.breakpoint_list.append({ 'file': file, 'line': line, 'id': breakpoint.GetID() })
                    else:
                        self.log_error('Cannot create breakpoint')

            self.update_window('breakpoint')
            self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
        else:
            self.log_error('No target selected')

    def buffer_sync(self):
        self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
        self.update_process_cursor()
        if self.process_info['state'] != 'exited':
            self.lock_files()

    def breakpoint_sync_back(self):
        if not self.is_window():
            if self.sync_back_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list):
                self.update_window('breakpoint')

    def goto_selected_frame(self):
        if self.process_info['state'] != 'exited':
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_frame_info = self.selected_frame_info_list[selected_thread_index]
            if selected_frame_info and selected_frame_info['type'] == 'full':
                self.goto_file(selected_frame_info['file'], selected_frame_info['line'], selected_frame_info['column'])

    def stack_window_goto_frame(self):
        if self.process_info['state'] != 'exited':
            frame_index = self.get_line() - 1
            frame_info = self.selected_thread_info['frames'][frame_index]
            if frame_info['type'] == 'full':
                selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
                if self.selected_frame_info_list[selected_thread_index] != frame_info:
                    self.selected_frame_info_list[selected_thread_index] = frame_info
                    self.update_window('stack')
                    self.update_window('watch')
                self.goto_selected_frame()

    def stack_window_next_thread(self):
        if self.process_info['state'] != 'exited':
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_thread_index = (selected_thread_index + 1) % len(self.process_info['threads'])
            self.selected_thread_info = self.process_info['threads'][selected_thread_index]
            self.update_window('stack')
            self.update_window('watch')
            self.goto_selected_frame()

    def stack_window_prev_thread(self):
        if self.process_info['state'] != 'exited':
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_thread_index = (selected_thread_index - 1 + len(self.process_info['threads'])) % len(self.process_info['threads'])
            self.selected_thread_info = self.process_info['threads'][selected_thread_index]
            self.update_window('stack')
            self.update_window('watch')
            self.goto_selected_frame()

    def breakpoint_window_goto_breakpoint(self):
        breakpoint_index = self.get_line() - 1
        breakpoint = self.breakpoint_list[breakpoint_index]
        self.goto_file(breakpoint['file'], breakpoint['line'], 0)

    def breakpoint_window_remove_breakpoint(self):
        breakpoint_index = self.get_line() - 1
        breakpoint = self.breakpoint_list[breakpoint_index]
        if self.selected_target['handle'].BreakpointDelete(breakpoint['id']):
            self.breakpoint_list.remove(breakpoint)
            self.update_window('breakpoint')
            self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
        else:
            self.log_error('Cannot remove breakpoint')

    def watch_window_add_watch(self):
        expr = self.call('input', 'Please add watch expression:\n')
        self.watch_list.append(expr)
        self.update_window('watch')

    def watch_window_change_watch(self):
        if len(self.watch_list):
            watch_index = self.get_line() - 1
            expr = self.call('input', 'Please change watch expression:\n', self.watch_list[watch_index])
            self.watch_list[watch_index] = expr
            self.update_window('watch')

    def watch_window_remove_watch(self):
        if len(self.watch_list):
            watch_index = self.get_line() - 1
            del self.watch_list[watch_index]
            self.update_window('watch')

    def handle_process_stopped(self, process_info, stopped_thread_info):
        def get_top_frame(thread_info):
            for frame_info in thread_info['frames']:
                if frame_info['type'] == 'full':
                    return frame_info
            return None

        if self.thread_guard():
            self.process_info = process_info
            self.selected_thread_info = stopped_thread_info
            self.selected_frame_info_list = [get_top_frame(thread_info) for thread_info in process_info['threads']]
            self.update_window('stack')
            self.update_window('watch')
            self.update_process_cursor()
            self.goto_selected_frame()

    def handle_process_exited(self):
        if self.thread_guard():
            self.process_info = self.EXITED_PROCESS_INFO
            self.selected_thread_info = None
            self.selected_frame_info_list = []
            self.update_window('stack')
            self.update_window('watch')
            self.update_process_cursor()
            self.unlock_files()

def event_loop(context):
    def get_process_info(process):
        process_state_dictionary = {
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

        process_info = {}
        stopped_thread_info = None
        process_info['state'] = process_state_dictionary[process.GetState()]
        process_info['threads'] = []
        for thread in process:
            thread_info = {}
            process_info['threads'].append(thread_info)

            thread_info['handle'] = thread
            thread_info['id'] = thread.GetIndexID()
            thread_info['tid'] = thread.GetThreadID()

            thread_info['frames'] = []
            for frame in thread:
                frame_info = {}
                thread_info['frames'].append(frame_info)

                frame_info['handle'] = frame
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
                stopped_thread_info = thread_info
        return process_info, stopped_thread_info

    try:
        context.log_info(f'event thread id: {threading.current_thread().ident}')
        listener = context.debugger.GetListener()
        listener.StartListeningForEvents(context.exit_broadcaster, 0xffffffff)
        while True:
            event = lldb.SBEvent()
            if listener.WaitForEvent(1, event):
                if lldb.SBProcess.EventIsProcessEvent(event):
                    event_type = event.GetType();
                    if event_type == lldb.SBProcess.eBroadcastBitStateChanged:
                        process = lldb.SBProcess.GetProcessFromEvent(event)
                        state = lldb.SBProcess.GetStateFromEvent(event)

                        if state == lldb.eStateStopped:
                            context.handle_process_stopped(*get_process_info(process))
                        elif state == lldb.eStateExited:
                            context.handle_process_exited()
                        elif state == lldb.eStateRunning:
                            pass
                elif event.BroadcasterMatchesRef(context.exit_broadcaster):
                    break
    except Exception:
        context.log_error(traceback.format_exc())

