/*
1) launch process (command line argument, environment variable, working directory)
2) step over/in/out
3) breakpoint toggle (line, function) 4) watch variable, navigate struct, array
*/

#include <cstdio>
#include <cstring>
#include <cassert>
#include <cstdint>
#include <unistd.h>
#include <pthread.h>
#include <LLDB.h>
using namespace lldb;

#include "util.cpp"
#include "msg.cpp"

char *translate_process_state(StateType state_type)
{
    switch (state_type)
    {
    case eStateInvalid:
        return "invalid";
    case eStateUnloaded:
        return "unloaded";
    case eStateConnected:
        return "connected";
    case eStateAttaching:
        return "attaching";
    case eStateLaunching:
        return "launching";
    case eStateStopped:
        return "stopped";
    case eStateRunning:
        return "running";
    case eStateStepping:
        return "stepping";
    case eStateCrashed:
        return "crashed";
    case eStateDetached:
        return "detached";
    case eStateExited:
        return "exited";
    case eStateSuspended:
        return "suspended";
    default:
        assert(false);
        return nullptr;
    }
}

struct Context
{
    SBDebugger debugger;
    SBTarget target;
    SBProcess process;
};

void log(char *message)
{
    int length = strlen(message);
    char buffer[length + sizeof(MsgInt)];
    *(MsgInt *)buffer = length;
    memcpy(buffer + sizeof(MsgInt), message, length);
    write(STDOUT_FILENO, buffer, length + sizeof(MsgInt));
}

void *response_loop(void * arg)
{
    Context *context = (Context *)arg;

    SBListener listener = context->debugger.GetListener();
    Array<char> msg_buffer = create_array<char>(4096);
    while (true)
    {
        SBEvent event;
        if (listener.WaitForEvent(1, event))
        {
            array_reset(&msg_buffer);

            if (SBProcess::EventIsProcessEvent(event))
            {
                uint32_t event_type = event.GetType();
                switch (event_type)
                {
                case SBProcess::eBroadcastBitStateChanged:
                    {
                        msg_pack_struct(&msg_buffer, 2);

                        msg_pack_key(&msg_buffer, "event", strlen("event"));
                        msg_pack_string(&msg_buffer, "state-changed", strlen("state-changed"));

                        msg_pack_key(&msg_buffer, "state", strlen("state"));
                        char *process_state = translate_process_state(context->process.GetStateFromEvent(event));
                        msg_pack_string(&msg_buffer, process_state, strlen(process_state));
                    }
                    break;
                }
            }

            if (msg_buffer.length)
            {
                MsgInt msg_length = msg_buffer.length;
                int byte_written = write(STDOUT_FILENO, &msg_length, sizeof(MsgInt));
                if (byte_written == sizeof(MsgInt))
                {
                    byte_written = write(STDOUT_FILENO, msg_buffer.data, msg_length);
                    if (byte_written == sizeof(msg_length))
                    {
                        // TODO: Handle error?
                    }
                }
            }
        }
    }
    return nullptr;
}

int main()
{
    Context context;

    SBDebugger::Initialize();
    context.debugger = SBDebugger::Create();
    context.debugger.SetAsync(true);

    pthread_t response_thread;
    int ret = pthread_create(&response_thread, nullptr, response_loop, &context);

    char *msg_buffer = nullptr;
    while (true)
    {
        MsgInt msg_length = 0;
        int byte_read = read(STDIN_FILENO, &msg_length, sizeof(MsgInt));
        if (byte_read == sizeof(MsgInt))
        {
            msg_buffer = (char *)realloc(msg_buffer, msg_length);
            byte_read = read(STDIN_FILENO, msg_buffer, msg_length);
            if (byte_read == msg_length)
            {
                MsgStruct *event = &msg_unpack(msg_buffer)->struct_data;
                MsgString *event_type = &msg_struct_data(event, "type")->string_data;

                if (strcmp(event_type->data, "launch") == 0)
                {
                    MsgString *msg_executable = &msg_struct_data(event, "executable")->string_data;
                    MsgArray *msg_arguments = &msg_struct_data(event, "arguments")->array_data;
                    MsgString *msg_working_dir = &msg_struct_data(event, "working_dir")->string_data;
                    MsgArray *msg_environments = &msg_struct_data(event, "environments")->array_data;

                    context.target = context.debugger.CreateTarget(msg_executable->data);

                    char *arguments[msg_arguments->length + 1];
                    for (int i = 0; i < msg_arguments->length; i++)
                    {
                        arguments[i] = msg_arguments[i].data->string_data.data;
                    }
                    arguments[msg_arguments->length] = 0;

                    char *environments[msg_environments->length + 1];
                    for (int i = 0; i < msg_environments->length; i++)
                    {
                        environments[i] = msg_environments[i].data->string_data.data;
                    }
                    environments[msg_environments->length] = 0;

                    SBError error;
                    SBListener invalid_listener;
                    context.process = context.target.Launch(invalid_listener, (const char **)arguments, (const char **)environments, 
                            nullptr, nullptr, nullptr, msg_working_dir->data, 0, false, error);
                }
                else if (strcmp(event_type->data, "step_over") == 0)
                {
                    SBThread thread = context.process.GetThreadAtIndex(0);
                    SBError error;
                    thread.StepOver(eOnlyDuringStepping, error);
                }
                else if (strcmp(event_type->data, "step_into") == 0)
                {
                    SBThread thread = context.process.GetThreadAtIndex(0);
                    thread.StepInto();
                }
                else if (strcmp(event_type->data, "step_out") == 0)
                {
                    SBThread thread = context.process.GetThreadAtIndex(0);
                    SBError error;
                    thread.StepOut(error);
                }
                else if (strcmp(event_type->data, "kill") == 0)
                {
                    SBError error = context.process.Kill();
                }
            }
            else
            {
                break;
            }
        }
        else
        {
            break;
        }
    }
}

