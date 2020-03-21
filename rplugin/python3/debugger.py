import os
import threading
import lldb

# TODO
# Ask Greg:
# 1. resource management (e.g. SBTarget), error handling, Python C++ interface
# 2. multiple processes per target?

class Context:
    def __init__(self, nvim):
        self.nvim = nvim

        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)
        self.target = None

        self.event_loop = threading.Thread(target=event_loop, args=(self,))
        self.event_loop.start()

    def log(self, value):
        self.nvim.command(f'echom {repr(value)}')

    def async_log(self, value):
        self.nvim.async_call(Context.log, self, value)

    def launch(self, executable, arguments, working_dir, environments):
        self.target = self.debugger.CreateTargetWithFileAndTargetTriple(executable, "x86_64-unknown-linux-gnu")

        launch_info = lldb.SBLaunchInfo()
        launch_info.SetExecutableFile(SBFileSpec(executable), True)
        launch_info.SetArguments(arguments, True)
        launch_info.SetEnvironmentEntries(environments, True)
        launch_info.SetWorkingDirectory(working_dir)
        launch_info.SetLaunchFlags(lldb.eLaunchFlagStopAtEntry)

        error = lldb.SBError()
        self.target.Launch(launch_info, error)
        if error.Fail():
            # TODO: Error reporting
            pass

    def step_over(self):
        process = self.target.GetProcess()
        thread = process.GetSelectedThread();
        error = lldb.SBError()
        thread.StepOver(lldb.eOnlyDuringStepping, error)
        if error.Fail():
            # TODO: Error reporting
            pass

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

    listener = context.debugger.GetListener()
    while True:
        event = lldb.SBEvent()
        if listener.WaitForEvent(1, event):
            if lldb.SBProcess.EventIsProcessEvent(event):
                event_type = event.GetType();
                if event_type == lldb.SBProcess.eBroadcastBitStateChanged:
                    process = lldb.SBProcess.GetProcessFromEvent(event)
                    state = lldb.SBProcess.GetStateFromEvent(event)
                    context.async_log(process_state_str(state))

