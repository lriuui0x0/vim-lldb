/*
1) launch process (command line argument, environment variable, working directory)
2) step over/in/out
3) breakpoint toggle (line, function)
4) watch variable, navigate struct, array
*/

#include <cstdio>
#include <unistd.h>
#include "msg.cpp"

#include <LLDB.h>
using namespace lldb;

int main()
{
    SBDebugger debugger = SBDebugger::Create();

    while (true)
    {
        MsgInt msg_length = 0;
        int byte_read = read(STDIN_FILENO, &msg_length, sizeof(MsgInt));
        if (byte_read == sizeof(MsgInt))
        {
            MsgBuffer msg_buffer = msg_buffer_create();
            msg_buffer_reserve(&msg_buffer, msg_length);
            byte_read = read(STDIN_FILENO, msg_buffer.data, msg_length);
            if (byte_read == msg_length)
            {
                MsgStruct *event = &msg_unpack(msg_buffer.data)->struct_data;
                MsgString *event_type = &msg_struct_data(event, "type")->string_data;

                if (strcmp(event_type->data, "launch") == 0)
                {
                    MsgString *executable = &msg_struct_data(event, "executable")->string_data;
                    MsgString *working_dir = &msg_struct_data(event, "working_dir")->string_data;
                    MsgArray *arguments = &msg_struct_data(event, "arguments")->array_data;
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

