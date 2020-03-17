import sys
from os import path
sys.path.append(path.dirname(__file__))

import os
import threading
from enum import Enum
import msg

class Debugger:
    def __init__(self, nvim, pid, fd_in, fd_out):
        self.nvim = nvim
        self.pid = pid
        self.fd_in = fd_in
        self.fd_out = fd_out
        self.response_loop = threading.Thread(target=response_loop, args=(self,))
        self.response_loop.start()

    def log(self, value):
        self.nvim.command(f'echom {repr(value)}')

    def async_log(self, value):
        self.nvim.async_call(Debugger.log, self, value)


def response_loop(debugger):
    while True:
        msg_bytes = os.read(debugger.fd_in, 8)
        if len(msg_bytes) < 8:
            break
        header_length, _ = msg.msg_unpack_int(msg_bytes)
        debugger.async_log(f'response loop, header_length = {header_length}')

        msg_bytes = os.read(debugger.fd_in, header_length)
        if len(msg_bytes) < header_length:
            break
        event, _ = msg.msg_unpack(msg_bytes)
        debugger.async_log(f'response loop, event = {event}')

def startup(nvim):
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

def send_event(debugger, event):
    event_bytes = msg.msg_pack(event)
    header_bytes = msg.msg_pack_int(len(event_bytes))
    os.write(debugger.fd_out, header_bytes)
    os.write(debugger.fd_out, event_bytes)


def launch(debugger, executable, arguments, working_dir, environments):
    event = {'type': 'launch', 'executable': executable, 'arguments': arguments, 'working_dir': working_dir, 'environments': environments}
    send_event(debugger, event)

def step_over(debugger):
    event = {'type': 'step_over'}
    send_event(debugger, event)

def step_into(debugger):
    event = {'type': 'step_into'}
    send_event(debugger, event)

def step_out(debugger):
    event = {'type': 'step_out'}
    send_event(debugger, event)

def kill(debugger):
    event = {'type': 'kill'}
    send_event(debugger, event)

