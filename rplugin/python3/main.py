import sys
import os
from os import path
import threading
import msg

class Debugger:
    def __init__(self, nvim, pid, fd_in, fd_out):
        self.nvim = nvim
        self.pid = pid
        self.fd_in = fd_in
        self.fd_out = fd_out
        self.event_loop = threading.Thread(target=debugger_event_loop, args=(self,))
        self.event_loop.start()

def change_line(debugger):
    debugger.nvim.call('TestFunc')

def debugger_event_loop(debugger):
    debugger.nvim.async_call(change_line, debugger)

def start(nvim):
    child_in, parent_out = os.pipe()
    parent_in, child_out = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(parent_in)
        os.close(parent_out)
        os.dup2(child_in, sys.stdin.fileno())
        os.dup2(child_out, sys.stdout.fileno())

        vim_lldb = path.abspath(path.join(path.dirname(__file__), '..', '..', 'bin', 'vim-lldb'))
        os.execl(vim_lldb, vim_lldb)
    else:
        os.close(child_in)
        os.close(child_out)

        debugger = Debugger(nvim, pid, parent_in, parent_out)
        return debugger

def launch(debugger, executable, working_dir, arguments):
    event_bytes = msg.msg_pack({'type': 'launch', 'executable': executable, 'working_dir': working_dir, 'arguments': arguments})
    header_bytes = msg.msg_pack_int(len(event_bytes))
    os.write(debugger.fd_out, header_bytes)
    os.write(debugger.fd_out, event_bytes)

    # print(os.read(debugger.fd_in, 1000).decode())

# debugger = start()
# launch(debugger, 'abcd', '/root', [1, 2, 3])

