import os
import re
import threading
import traceback
import inspect
from contextlib import contextmanager
import time
import lldb

def list_replace(list, old_value, new_value):
    try:
        index = list.index(old_value)
        list[index] = new_value
    except ValueError:
        pass

# TODO
# resource management (e.g. SBTarget), error handling (SBError vs IsValid), Python C++ interface
# multiple processes per target?
# passing string (and other elements) through API
# guarantee only one thread may have stop reason?
# does GetThreadID change when some thread dies?
# module.GetFileSpec() vs module.GetPlatformFileSpec()?
# relationship between SBSymbol, SBModule, SBSymbolContext
# differences between all the step functions
# Why does StepInto not fail
# Any case where MightHaveChildren returns True but acutal children number is 0?
# What is use_dynamic for variable inspection?

# TODO
# Stepping problem, two handler can be called in the interleaved fashion, wtf? Currently solved through async_lock, https://github.com/neovim/pynvim/issues/441
# matchdelete in nvim https://github.com/neovim/neovim/issues/12110
# switch to win_execute in nvim
# Configurable debugger window layout, window key mapping
# Log breakpoint attach failure (is IsValid the right function to use?)
# scrolling output window, can be solved by win_execute
# Investigate wrong frame information, image lookup --verbose --address <pc>

class Context:
    VIM_LLDB_WINDOW_KEY = 'vim_lldb'
    VIM_LLDB_WINDOW_LOCK = 'vim_lldb_window_lock'
    VIM_LLDB_WINDOW_MATCH = 'vim_lldb_window_match'
    VIM_LLDB_SIGN_BREAKPOINT = 'vim_lldb_sign_breakpoint'
    VIM_LLDB_SIGN_CURSOR_SELECTED = 'vim_lldb_sign_cursor_selected'
    VIM_LLDB_SIGN_CURSOR_NOT_SELECTED = 'vim_lldb_sign_cursor_not_selected'

    def __init__(self, nvim):
        self.nvim = nvim
        self.tid = threading.current_thread().ident
        self.async_lock = threading.Lock()

        self.sign_id = 0
        self.command(f'highlight {self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT guifg=red')
        self.call('sign_define', self.VIM_LLDB_SIGN_BREAKPOINT, {'text': '●', 'texthl': f'{self.VIM_LLDB_SIGN_BREAKPOINT}_HIGHLIGHT'})
        self.command(f'highlight {self.VIM_LLDB_SIGN_CURSOR_SELECTED}_HIGHLIGHT guifg=yellow')
        self.call('sign_define', self.VIM_LLDB_SIGN_CURSOR_SELECTED, {'text': '➨', 'texthl': f'{self.VIM_LLDB_SIGN_CURSOR_SELECTED}_HIGHLIGHT'})
        self.command(f'highlight {self.VIM_LLDB_SIGN_CURSOR_NOT_SELECTED}_HIGHLIGHT guifg=lightgreen')
        self.call('sign_define', self.VIM_LLDB_SIGN_CURSOR_NOT_SELECTED, {'text': '➨', 'texthl': f'{self.VIM_LLDB_SIGN_CURSOR_NOT_SELECTED}_HIGHLIGHT'})

        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)
        self.is_debugger_toggling = False

        self.targets = []
        self.selected_target = None
        self.select_target()

        self.process_info = { 'state': 'exited', 'threads': [] }
        self.selected_thread_info = None
        self.selected_frame_info_list = []
        self.breakpoint_list = []
        self.watch_list = []
        self.process_output = { 'both': '', 'stdout': '', 'stderr': '' }
        self.selected_stream = 'both'

        self.exit_broadcaster = lldb.SBBroadcaster('exit_broadcaster')
        self.event_loop = threading.Thread(target=event_loop, args=(self,))
        self.event_loop.start()

    def command(self, cmd):
        self.nvim.command(cmd)

    def call(self, func, *args):
        return self.nvim.call(func, *args)

    # NOTE: Use this funtion if the the Context method can be called from the event loop thread, it will automatcially dispatch an async_call if it's indeed called from event thread
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

    # NOTE: Pynvim echomsg doesn't handle multi-line string correctly, split into multiple lines
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
        if self.thread_guard():
            if type(value) == str:
                for line in self.to_lines(value):
                    # NOTE: echoerr seems to be treated as throwing error, so we have to use echomsg instead
                    self.command(f'echohl ErrorMsg')
                    self.command(f'echomsg {line}')
                    self.command(f'echohl Normal')
            else:
                self.command(f'echohl ErrorMsg')
                self.command(f'echomsg {repr(value)}')
                self.command(f'echohl Normal')

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

    def get_column(self):
        return self.call('col', '.')

    def get_column_count(self):
        return self.call('col', '$')

    def set_line_column(self, line, column):
        self.call('cursor', line, column)

    def get_window_var(self, window, var):
        return self.call('getwinvar', window, var)

    def set_window_var(self, window, var, value):
        return self.call('setwinvar', window, var, value)

    def get_buffer_file(self, buffer = 0):
        buffer = buffer or self.get_buffer()
        return os.path.abspath(self.call('bufname', buffer))

    # NOTE: Sync a list of signs in memory to screen
    def sync_signs(self, sign_type, sign_list):
        buffer_count = self.get_buffer_count()
        for buffer in range(1, buffer_count + 1):
            if self.is_buffer_valid(buffer):
                # NOTE: We need to calculate the diff between the signs on screen and signs in memory, since we can't just remove all signs and add new signs all together, which causes a visual flash for unchanged signs
                buffer_curr_sign_list = self.call('sign_getplaced', buffer, { 'group': sign_type })[0]['signs']
                buffer_sign_list = [sign for sign in sign_list if sign['file'] == self.get_buffer_file(buffer)]

                # NOTE: Calculate signs on screen to remove
                for buffer_curr_sign in buffer_curr_sign_list:
                    found = False
                    for buffer_sign in buffer_sign_list:
                        if buffer_curr_sign['lnum'] == buffer_sign['line']:
                            found = True
                            break
                    if not found:
                        self.call('sign_unplace', sign_type, { 'buffer': buffer, 'id': buffer_curr_sign['id'] })

                # NOTE: Calculate signs in memory to add
                for buffer_sign in buffer_sign_list:
                    found = False
                    for buffer_curr_sign in buffer_curr_sign_list:
                        if buffer_sign['line'] == buffer_curr_sign['lnum']:
                            found = True
                            break
                    if not found:
                        self.sign_id += 1
                        # NOTE: Process cursor shows on top of breakpoint
                        priorities = {self.VIM_LLDB_SIGN_BREAKPOINT: 1000, self.VIM_LLDB_SIGN_CURSOR_SELECTED: 2000, self.VIM_LLDB_SIGN_CURSOR_NOT_SELECTED: 2000}
                        self.call('sign_place', self.sign_id, sign_type, sign_type, buffer,
                             { 'lnum': buffer_sign['line'], 'priority': priorities[sign_type]})

    # NOTE: Sync signs on screen back to memory
    def sync_back_signs(self, sign_type, sign_list):
        buffer = self.get_buffer()
        buffer_curr_sign_list = sorted(self.call('sign_getplaced', buffer, { 'group': sign_type })[0]['signs'], key=lambda x: x['lnum'])
        buffer_sign_list = sorted([sign for sign in sign_list if sign['file'] == self.get_buffer_file(buffer)], key=lambda x: x['line'])

        # NOTE: Since this function will only be called when text is changed, we assume the number of signs on screen and in memory are already aligned, so we only adjust the line number
        has_change = False
        for i in range(len(buffer_sign_list)):
            if buffer_sign_list[i]['line'] != buffer_curr_sign_list[i]['lnum']:
                buffer_sign_list[i]['line'] = buffer_curr_sign_list[i]['lnum']
                has_change = True

        # NOTE: Let caller know if update is needed
        return has_change

    def goto_file(self, file, line, column):
        # NOTE: Show file in current window > last window > new window
        window = 0
        test_window = self.get_window()
        if not self.get_window_var(test_window, self.VIM_LLDB_WINDOW_KEY):
            window = test_window
        else:
            test_window = self.get_last_window()
            if not self.get_window_var(test_window, self.VIM_LLDB_WINDOW_KEY):
                window = test_window
            else:
                window_count = self.get_window_count()
                for test_window in range(1, window_count + 1):
                    if not self.get_window_var(test_window, self.VIM_LLDB_WINDOW_KEY):
                        window = test_window
                        break
        if window:
            self.command(f'{window} wincmd w')
        else:
            self.command('vnew')
            window = self.get_window()

        # NOTE: Find existing buffer if possible, otherwise edit new buffer
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

        self.set_line_column(line, column)

    def is_debugger_window(self, name = ''):
        window = self.get_window()
        window_name = self.get_window_var(window, self.VIM_LLDB_WINDOW_KEY)
        return window_name and (name == '' or window_name == name)

    def check_window_exists(self, name = ''):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            window_name = self.get_window_var(window, self.VIM_LLDB_WINDOW_KEY)
            if window_name:
                if name == '' or window_name == name:
                    return window
        return 0

    def create_window(self, name):
        window = self.get_window()
        self.set_window_var(window, '&readonly', 1)
        self.set_window_var(window, '&modifiable', 0)
        self.set_window_var(window, '&buftype', 'nofile')
        self.set_window_var(window, '&buflisted', 0)
        self.set_window_var(window, '&bufhidden', 'wipe')
        self.set_window_var(window, '&swapfile', 0)
        self.set_window_var(window, '&number', 0)
        self.set_window_var(window, '&ruler', 0)
        self.set_window_var(window, '&wrap', 0)

        self.command(f'file vim-lldb ({name})')
        self.set_window_var(window, self.VIM_LLDB_WINDOW_KEY, name)

        # NOTE: We can use <nowait> in the future if we want to map 'd' into a shortcut
        if name == 'stack':
            self.command('nnoremap <buffer> <CR> :call VimLLDB_StackWindow_GotoFrame()<CR>')
            self.command('nnoremap <buffer> <C-n> :call VimLLDB_StackWindow_NextThread()<CR>')
            self.command('nnoremap <buffer> <C-p> :call VimLLDB_StackWindow_PrevThread()<CR>')
        elif name == 'breakpoint':
            self.command('nnoremap <buffer> <CR> :call VimLLDB_BreakpointWindow_GotoBreakpoint()<CR>')
            self.command('nnoremap <buffer> md :call VimLLDB_BreakpointWindow_RemoveBreakpoint()<CR>')
        elif name == 'watch':
            self.command('nnoremap <buffer> ma :call VimLLDB_WatchWindow_AddWatch()<CR>')
            self.command('nnoremap <buffer> mm :call VimLLDB_WatchWindow_ChangeWatch()<CR>')
            self.command('nnoremap <buffer> md :call VimLLDB_WatchWindow_RemoveWatch()<CR>')
            self.command('nnoremap <buffer> o :call VimLLDB_WatchWindow_ExpandWatch()<CR>')
            self.command('nnoremap <buffer> x :call VimLLDB_WatchWindow_CollapseWatch()<CR>')
        elif name == 'output':
            self.command('nnoremap <buffer> <C-n> :call VimLLDB_OutputWindow_NextStream()<CR>')
            self.command('nnoremap <buffer> <C-p> :call VimLLDB_OutputWindow_PrevStream()<CR>')

    def destory_window(self, name = ''):
        while True:
            window_count = self.get_window_count()
            for window in range(1, window_count + 1):
                window_name = self.get_window_var(window, self.VIM_LLDB_WINDOW_KEY)
                if window_name and (name == '' or window_name == name):
                    if window_count > 1:
                        self.command(f'{window}quit!')
                    else:
                        self.command(f'enew!')
                    break
            if window_count == 1:
                break

    def update_window(self, name):
        def get_output_window_lines():
            lines = [ { 'text': f'process output {self.selected_stream}' }, { 'text': '' } ]
            for text in self.process_output[self.selected_stream].splitlines():
                lines.append({'text': text })
            return lines

        def get_breakpoint_window_lines():
            lines = []
            for breakpoint in self.breakpoint_list:
                lines.append({'text': f'{breakpoint["file"]}:{breakpoint["line"]}' })
            return lines

        def get_stack_window_lines():
            lines = []
            if self.process_info['state'] == 'stopped':
                selected_frame_info = self.get_selected_frame_info()
                for line, frame_info in enumerate(self.selected_thread_info['frames'], start=1):
                    if frame_info['type'] == 'full':
                        line = { 'text': f'{frame_info["function"]}  ({frame_info["file"]}:{frame_info["line"]})' }
                        if frame_info == selected_frame_info:
                            line['text'] += '  *'
                    else:
                        line = { 'text': f'{frame_info["function"]}  ({frame_info["module"]})', 'highlight': 'invalid' }
                    lines.append(line)
                lines.append({ 'text': '' })
                lines.append({ 'text': f'thread {self.selected_thread_info["id"]}' })
            else:
                lines.append({ 'text': f'process {self.process_info["state"]}' })
            return lines

        def get_watch_window_lines():
            lines = []
            def add_watch_list_lines(watch_list, depth):
                indent = '  ' * depth
                for watch in watch_list:
                    if self.process_info['state'] == 'stopped':
                        if watch['value'].IsValid():
                            summary = watch['value'].GetSummary()
                            value = watch['value'].GetValue()
                            if watch['value'].MightHaveChildren():
                                summary = f'  {summary}' if summary else (f'  {value}' if value else '')
                                if watch['children']:
                                    lines.append({ 'text': f'{indent}{watch["expr"]}{summary}' })
                                    add_watch_list_lines(watch['children'], depth + 1)
                                else:
                                    lines.append({ 'text': f'{indent}{watch["expr"]}{summary}  ...' })
                            else:
                                lines.append({ 'text': f'{indent}{watch["expr"]}  {value}' })
                        else:
                            lines.append({ 'text': f'{indent}{watch["expr"]}' })
                    else:
                        lines.append({ 'text': f'{indent}{watch["expr"]}' })
                        add_watch_list_lines(watch['children'], depth + 1)
            add_watch_list_lines(self.watch_list, 0)
            return lines

        # NOTE: All debugger window are non-modifiable. Modify the window through a temporary modifiable environment
        @contextmanager
        def writing(window):
            saved_line = self.get_line()
            saved_column = self.get_column()

            self.set_window_var(window, '&readonly', 0)
            self.set_window_var(window, '&modifiable', 1)
            yield
            self.set_window_var(window, '&readonly', 1)
            self.set_window_var(window, '&modifiable', 0)
            self.set_window_var(window, '&modified', 0)

            self.set_line_column(saved_line, saved_column)

        window = self.check_window_exists(name)
        if window:
            if name == 'stack':
                lines = get_stack_window_lines()
            elif name == 'breakpoint':
                lines = get_breakpoint_window_lines()
            elif name == 'watch':
                lines = get_watch_window_lines()
            elif name == 'output':
                lines = get_output_window_lines()

            window_matches = self.get_window_var(window, self.VIM_LLDB_WINDOW_MATCH)
            if window_matches:
                for match in window_matches:
                    self.call('matchdelete', match, window)
            window_matches = []

            with writing(window):
                # NOTE: We use deletebufline and setbufline instead of navigating to the window so that we don't see a flash of cursor change
                buffer = self.call('winbufnr', window)
                self.call('deletebufline', buffer, 1, '$')
                for line_index, line in enumerate(lines, start=1):
                    self.call('setbufline', buffer, line_index, line['text'])
                    if 'highlight' in line:
                        highlight_dictionary = {
                            'invalid': 'Comment'
                        }
                        # TODO: Add this code when matchdelete works
                        # match_id = self.call('matchaddpos', highlight_dictionary[line['highlight']], [line_index], -1, -1, { 'window': window })
                        # window_matches.append(match_id)

            self.set_window_var(window, self.VIM_LLDB_WINDOW_MATCH, window_matches)

    # NOTE: Lock all potential cpp files as non-modifiable when the process runs, so that we don't get into situations like breakpoint and cursor signs don't match their source code line
    def lock_files(self):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            buffer = self.get_window_buffer(window)
            if re.compile(r'.*\.(c|cpp|cxx|h|hpp|hxx)$').match(self.get_buffer_file(buffer)):
                self.set_window_var(window, '&readonly', 1)
                self.set_window_var(window, '&modifiable', 0)
                self.set_window_var(window, self.VIM_LLDB_WINDOW_LOCK, 1)

    def unlock_files(self):
        window_count = self.get_window_count()
        for window in range(1, window_count + 1):
            if self.get_window_var(window, self.VIM_LLDB_WINDOW_LOCK):
                self.set_window_var(window, '&readonly', 0)
                self.set_window_var(window, '&modifiable', 1)
                self.set_window_var(window, self.VIM_LLDB_WINDOW_LOCK, 0)
                
    def select_target(self, selection = 0):
        # NOTE: Load target definitions when we select target so that we don't need a separate funtion to refresh target definitions 
        if self.call('exists', 'g:vim_lldb_targets'):
            targets = self.call('eval', 'g:vim_lldb_targets')
        else:
            self.log_error('No target definition')
            return

        if type(targets) == list and all(map(lambda target: type(target) == dict and set(target) == { 'name', 'executable', 'arguments', 'working_dir', 'environments' }, targets)):
            self.targets = targets
        else:
            self.log_error('Incorrect target format')
            return

        if type(selection) == int:
            if selection >= 0 and selection < len(self.targets):
                self.selected_target = self.targets[selection]
            else:
                self.log_error('Target index out of bound')
        elif type(selection) == str:
            matched_targets = [target for target in self.targets if target.name == selection]
            if len(matched_targets) == 1:
                self.selected_target = matched_targets
            else:
                self.log_error('Target name not found' if len(matched_targets) == 0 else 'Ambiguous target name')
        else:
            self.log_error('Invalid target selection')

    def toggle_debugger(self):
        if not self.is_debugger_toggling:
            self.is_debugger_toggling = True
            if self.selected_target:
                if self.check_window_exists():
                    self.destory_window()
                else:
                    window = self.get_window()

                    self.command('vnew')
                    # NOTE: We need to update the window immediately after the window is created to avoid race condition of modifying a non-modifiable window. Why?
                    self.create_window('output')
                    self.update_window('output')

                    self.command('new')
                    self.create_window('breakpoint')
                    self.update_window('breakpoint')

                    self.command('new')
                    self.create_window('watch')
                    self.update_window('watch')

                    self.command('new')
                    self.create_window('stack')
                    self.update_window('stack')

                    self.command(f'{window} wincmd w')
            else:
                self.log_error('No target selected')
            self.is_debugger_toggling = False

    def launch(self):
        if self.selected_target:
            if self.process_info['state'] == 'exited':
                executable = self.selected_target['executable']
                arguments = self.selected_target['arguments']
                working_dir = self.selected_target['working_dir']
                environments = self.selected_target['environments']

                # NOTE: We simplify the breakpoint states by creating a new target (no breakpoint) every time we launch, and creating all breakpoints
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
                    self.process_output['both'] = ''
                    self.process_output['stdout'] = ''
                    self.process_output['stderr'] = ''
                    self.update_window('output')
                else:
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot launch process from non-exited state')
        else:
            self.log_error('No target selected')

    def step_over(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                thread = self.selected_thread_info['handle']
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
                thread = self.selected_thread_info['handle']
                thread.StepInto()
            else:
                self.log_error('Cannot step from non-stopped state')
        else:
            self.log_error('No target selected')

    def step_out(self):
        if self.selected_target:
            if self.process_info['state'] == 'stopped':
                thread = self.selected_thread_info['handle']
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

    def pause(self):
        if self.selected_target:
            if self.process_info['state'] == 'running':
                process = self.selected_target['handle'].GetProcess()
                error = process.Stop()
                if error.Fail():
                    self.log_error(error.GetCString())
            else:
                self.log_error('Cannot pause from non-running state')
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
        cursor_list_selected = []
        cursor_list_not_selected = []
        if self.process_info['state'] == 'stopped':
            selected_frame_info = self.get_selected_frame_info()
            for frame_info in self.selected_thread_info['frames']:
                if frame_info['type'] == 'full':
                    cursor_list = cursor_list_selected if frame_info == selected_frame_info else cursor_list_not_selected
                    cursor_list.append({ 'file': frame_info['file'], 'line': frame_info['line'] })
        self.sync_signs(self.VIM_LLDB_SIGN_CURSOR_SELECTED, cursor_list_selected)
        self.sync_signs(self.VIM_LLDB_SIGN_CURSOR_NOT_SELECTED, cursor_list_not_selected)

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
                    self.breakpoint_list.append({ 'file': file, 'line': line, 'id': None })
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
        if not self.is_debugger_window():
            self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
            self.update_process_cursor()
            if self.process_info['state'] != 'exited':
                self.lock_files()

    def buffer_sync_back(self):
        # NOTE: We don't want to sync back breakpoint window, otherwise update_window will keep triggerring buffer_sync_back, causing a dead loop
        if not self.is_debugger_window():
            if self.sync_back_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list):
                self.update_window('breakpoint')

    def get_selected_frame_info(self):
        if self.selected_thread_info:
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_frame_info = self.selected_frame_info_list[selected_thread_index]
            return selected_frame_info
        return None

    def goto_selected_frame(self):
        selected_frame_info = self.get_selected_frame_info()
        if selected_frame_info and selected_frame_info['type'] == 'full':
            self.goto_file(selected_frame_info['file'], selected_frame_info['line'], selected_frame_info['column'])

    def stack_window_goto_frame(self):
        if self.process_info['state'] == 'stopped':
            frame_index = self.get_line() - 1
            frame_info = self.selected_thread_info['frames'][frame_index]
            if frame_info['type'] == 'full':
                selected_frame_info = self.get_selected_frame_info()
                if selected_frame_info != frame_info:
                    list_replace(self.selected_frame_info_list, selected_frame_info, frame_info)
                    self.update_window('stack')
                    self.update_process_cursor()
                    self.reevaluate_watch_list()
                    self.update_window('watch')
                # NOTE: Always focus frame even selected frame is the same, since user may move away manually
                self.goto_selected_frame()

    def stack_window_next_thread(self):
        if self.process_info['state'] == 'stopped':
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_thread_index = (selected_thread_index + 1) % len(self.process_info['threads'])
            self.selected_thread_info = self.process_info['threads'][selected_thread_index]
            self.update_window('stack')
            self.update_process_cursor()
            self.goto_selected_frame()
            self.reevaluate_watch_list()
            self.update_window('watch')

    def stack_window_prev_thread(self):
        if self.process_info['state'] == 'stopped':
            selected_thread_index = self.process_info['threads'].index(self.selected_thread_info)
            selected_thread_index = (selected_thread_index - 1 + len(self.process_info['threads'])) % len(self.process_info['threads'])
            self.selected_thread_info = self.process_info['threads'][selected_thread_index]
            self.update_window('stack')
            self.update_process_cursor()
            self.goto_selected_frame()
            self.reevaluate_watch_list()
            self.update_window('watch')

    def breakpoint_window_goto_breakpoint(self):
        breakpoint_index = self.get_line() - 1
        breakpoint = self.breakpoint_list[breakpoint_index]
        self.goto_file(breakpoint['file'], breakpoint['line'], 0)

    def breakpoint_window_remove_breakpoint(self):
        breakpoint_index = self.get_line() - 1
        breakpoint = self.breakpoint_list[breakpoint_index]
        if self.process_info['state'] == 'exited':
            self.breakpoint_list.remove(breakpoint)
            self.update_window('breakpoint')
            self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
        else:
            if self.selected_target['handle'].BreakpointDelete(breakpoint['id']):
                self.breakpoint_list.remove(breakpoint)
                self.update_window('breakpoint')
                self.sync_signs(self.VIM_LLDB_SIGN_BREAKPOINT, self.breakpoint_list)
            else:
                self.log_error('Cannot remove breakpoint')

    def output_window_next_stream(self):
        stream_order = ['both', 'stdout', 'stderr']
        selected_stream_index = stream_order.index(self.selected_stream)
        selected_stream_index = (selected_stream_index + 1) % len(stream_order)
        self.selected_stream = stream_order[selected_stream_index]
        self.update_window('output')

    def output_window_prev_stream(self):
        stream_order = ['both', 'stdout', 'stderr']
        selected_stream_index = stream_order.index(self.selected_stream)
        selected_stream_index = (selected_stream_index - 1 + len(stream_order)) % len(stream_order)
        self.selected_stream = stream_order[selected_stream_index]
        self.update_window('output')

    # NOTE: Get watch in the nested structure from line number
    def get_watch(self, line = 0):
        if not line:
            line = self.get_line()
        found_watch = None
        def find_watch(watch_list, offset):
            nonlocal found_watch
            for watch in watch_list:
                if offset == line:
                    found_watch = watch
                if watch['children']:
                    offset = find_watch(watch['children'], offset + 1)
                else:
                    offset += 1
            return offset
        find_watch(self.watch_list, 1)
        return found_watch

    def evaluate_expr(self, expr):
        watch = { 'expr': expr, 'children': [], 'parent': None }
        if self.process_info['state'] == 'stopped':
            expr_list = expr.split('@')
            if len(expr_list) > 2:
                watch['value'] = None
            else:
                expr = expr_list[0]
                frame = self.get_selected_frame_info()['handle']
                # NOTE: Do not evaluate expression if the expression is variable-like to avoid parsing overhead
                if re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$').match(expr):
                    watch['value'] = frame.FindVariable(expr)
                else:
                    # NOTE: GetValueForVariablePath handles simple field accessor expressions (-> . * & [])
                    watch['value'] = frame.GetValueForVariablePath(expr)
                    if not watch['value'].IsValid():
                        watch['value'] = frame.EvaluateExpression(expr)

                if len(expr_list) > 1:
                    comma_list = expr_list[1].split(',')
                    try:
                        if len(comma_list) == 2:
                            offset = int(comma_list[0])
                            length = int(comma_list[1])
                            if offset >= 0 and length > 0:
                                watch['special'] = { 'type': 'at', 'offset': offset, 'length': length }
                            else:
                                watch['value'] = None
                        elif len(comma_list) == 1:
                            length = int(comma_list[0])
                            if length > 0:
                                watch['special'] = { 'type': 'at', 'offset': 0, 'length': length }
                            else:
                                watch['value'] = None
                        else:
                            watch['value'] = None
                    except ValueError:
                        watch['value'] = None
        else:
            # NOTE: We return None here instead of raising error since we want to be able to modify the watch window from exited state. This simplifies the caller
            watch['value'] = None
        return watch

    def watch_window_add_watch(self):
        if self.process_info['state'] != 'running':
            expr = self.call('input', 'Please add watch expression:\n')
            # NOTE: Do not add watch when user cancels input or have empty input
            if expr:
                watch = self.evaluate_expr(expr)
                self.watch_list.append(watch)
                self.update_window('watch')
                # NOTE: Go to the newly added watch
                self.set_line_column(self.get_line_count(), 0)
        else:
            self.log_error('Cannot modify watch window from running state')

    def watch_window_change_watch(self):
        if self.process_info['state'] != 'running':
            if self.watch_list:
                watch = self.get_watch()
                while watch['parent']:
                    watch = watch['parent']
                expr = self.call('input', 'Please change watch expression:\n', watch['expr'])
                if expr:
                    new_watch = self.evaluate_expr(expr)
                    list_replace(self.watch_list, watch, new_watch)
                    self.update_window('watch')
        else:
            self.log_error('Cannot modify watch window from running state')

    def watch_window_remove_watch(self):
        if self.process_info['state'] != 'running':
            if self.watch_list:
                watch = self.get_watch()
                while watch['parent']:
                    watch = watch['parent']
                self.watch_list.remove(watch)
                self.update_window('watch')
        else:
            self.log_error('Cannot modify watch window from running state')

    def get_watch_children(self, watch):
        value = watch['value']
        if value and value.IsValid():
            if 'special' in watch:
                indices = list(range(watch['special']['offset'], watch['special']['offset'] + watch['special']['length']))
                children = [value.GetValueForExpressionPath(f'[{index}]') for index in indices]
                children = list(map(lambda v: { 'expr': v.GetName(), 'value': v, 'children': [], 'parent': watch }, children))
            else:
                if value.MightHaveChildren():
                    children = [value.GetChildAtIndex(index) for index in range(value.GetNumChildren())]
                    children = list(map(lambda v: { 'expr': v.GetName(), 'value': v, 'children': [], 'parent': watch }, children))
                else:
                    children = []
        else:
            children = []
        return children

    def watch_window_expand_watch(self):
        if self.process_info['state'] != 'running':
            watch = self.get_watch()
            if not watch['children']:
                watch['children'] = self.get_watch_children(watch)
                if watch['children']:
                    self.update_window('watch')
        else:
            self.log_error('Cannot modify watch window from running state')

    def watch_window_collapse_watch(self):
        if self.process_info['state'] != 'running':
            watch = self.get_watch()
            # NOTE: If current watch cannot be collapsed but there's parent, collapse parent instead
            if not watch['children'] and watch['parent']:
                watch = watch['parent']
            if watch['children']:
                watch['children'] = []
                self.update_window('watch')
        else:
            self.log_error('Cannot modify watch window from running state')

    # NOTE: Reevaluation takes care of the cases where the same variable mean different things in different frames. It maintains the watch structure as long as possible
    def reevaluate_watch_list(self):
        def expand_children(watch, curr_children):
            if curr_children:
                watch['children'] = self.get_watch_children(watch)
                for child in watch['children']:
                    match_child = None
                    for curr_child in curr_children:
                        if curr_child['expr'] == child['expr']:
                            match_child = curr_child
                            break
                    # NOTE: We want to expand child if the same name is expanded in the current watch structure
                    if match_child:
                        expand_children(child, match_child['children'])

        if self.process_info['state'] == 'stopped':
            for watch in self.watch_list:
                curr_children = watch['children']
                new_watch = self.evaluate_expr(watch['expr'])
                list_replace(self.watch_list, watch, new_watch)
                expand_children(new_watch, curr_children)

    def handle_process_stopped(self, process_info, stopped_thread_info):
        def get_top_frame(thread_info):
            for frame_info in thread_info['frames']:
                if frame_info['type'] == 'full':
                    return frame_info
            return None

        if self.thread_guard():
            self.process_info = process_info
            # NOTE: Select stopped thread and top frame (with debugging info) for each thread
            self.selected_thread_info = stopped_thread_info
            self.selected_frame_info_list = [get_top_frame(thread_info) for thread_info in process_info['threads']]
            self.update_window('stack')
            self.update_process_cursor()
            self.goto_selected_frame()
            self.reevaluate_watch_list()
            self.update_window('watch')
            self.async_lock.release()

    def handle_process_exited(self):
        if self.thread_guard():
            self.process_info = { 'state': 'exited', 'threads': [] }
            self.selected_thread_info = None
            self.selected_frame_info_list = []
            self.update_window('stack')
            self.update_process_cursor()
            self.reevaluate_watch_list()
            self.update_window('watch')
            self.unlock_files()
            self.async_lock.release()

    def handle_process_running(self):
        if self.thread_guard():
            self.process_info = { 'state': 'running', 'threads': [] }
            self.selected_thread_info = None
            self.selected_frame_info_list = []
            self.update_window('stack')
            self.update_process_cursor()
            self.update_window('watch')
            self.async_lock.release()

    def handle_process_stdout(self, output):
        if self.thread_guard():
            self.process_output['both'] += output
            self.process_output['stdout'] += output
            self.update_window('output')
            self.async_lock.release()

    def handle_process_stderr(self, output):
        if self.thread_guard():
            self.process_output['both'] += output
            self.process_output['stderr'] += output
            self.update_window('output')
            self.async_lock.release()

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

    def read_output(stream):
        output = ''
        output_chunk = stream(4096)
        while output_chunk:
            output += output_chunk
            output_chunk = stream(4096)
        return output

    try:
        listener = context.debugger.GetListener()
        listener.StartListeningForEvents(context.exit_broadcaster, 0xffffffff)
        while True:
            event = lldb.SBEvent()
            if listener.WaitForEvent(1, event):
                if lldb.SBProcess.EventIsProcessEvent(event):
                    process = lldb.SBProcess.GetProcessFromEvent(event)
                    event_type = event.GetType();
                    if event_type == lldb.SBProcess.eBroadcastBitStateChanged:
                        state = lldb.SBProcess.GetStateFromEvent(event)
                        if state == lldb.eStateStopped:
                            context.async_lock.acquire()
                            context.handle_process_stopped(*get_process_info(process))
                        elif state == lldb.eStateExited:
                            context.async_lock.acquire()
                            context.handle_process_exited()
                        elif state == lldb.eStateRunning:
                            context.async_lock.acquire()
                            context.handle_process_running()
                    elif event_type == lldb.SBProcess.eBroadcastBitSTDOUT:
                        context.async_lock.acquire()
                        context.handle_process_stdout(read_output(process.GetSTDOUT))
                    elif event_type == lldb.SBProcess.eBroadcastBitSTDERR:
                        context.async_lock.acquire()
                        context.handle_process_stderr(read_output(process.GetSTDERR))
                elif event.BroadcasterMatchesRef(context.exit_broadcaster):
                    break
    except Exception:
        context.log_error(traceback.format_exc())

