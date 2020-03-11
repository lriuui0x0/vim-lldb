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
        self.event_loop = threading.Thread(target=response_loop, args=(self,))
        self.event_loop.start()

def test_func(debugger, value):
    debugger.nvim.current.line = value.replace('\n', '')

def response_loop(debugger):
    while True:
        value = os.read(debugger.fd_in, 1000).decode()
        # header_length = msg.msg_unpack_int(os.read(debugger.fd_in, 8))
        # event = msg.msg_unpack(os.read(debugger.))
        debugger.nvim.async_call(test_func, debugger, value)

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

def launch(debugger, executable, arguments, working_dir, environments):
    event_bytes = msg.msg_pack({'type': 'launch', 'executable': executable, 'arguments': arguments, 'working_dir': working_dir, 'environments': environments})
    header_bytes = msg.msg_pack_int(len(event_bytes))
    os.write(debugger.fd_out, header_bytes)
    os.write(debugger.fd_out, event_bytes)

