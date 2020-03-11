/*
1) launch process (command line argument, environment variable, working directory)
2) step over/in/out
3) breakpoint toggle (line, function)
4) watch variable, navigate struct, array
*/

#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <pthread.h>
#include <LLDB.h>
using namespace lldb;

#include "util.cpp"
#include "msg.cpp"

void *response_loop(void * arg)
{
    SBListener *listener = (SBListener *)arg;
    SBEvent event;
    for (int i = 0; i < 5; i++)
    {
        printf("Hello");
    }
    return nullptr;
}

int main()
{
    SBDebugger::Initialize();
    SBDebugger debugger = SBDebugger::Create();
    debugger.SetAsync(true);
    SBListener listener = debugger.GetListener();

    pthread_t response_thread;
    int ret = pthread_create(&response_thread, nullptr, response_loop, &listener);

    while (true)
    {
        MsgInt msg_length = 0;
        int byte_read = read(STDIN_FILENO, &msg_length, sizeof(MsgInt));
        if (byte_read == sizeof(MsgInt))
        {
            Array<char> msg_buffer = create_array<char>(4096);
            array_reserve(&msg_buffer, msg_length);
            byte_read = read(STDIN_FILENO, msg_buffer.data, msg_length); if (byte_read == msg_length)
            {
                MsgStruct *event = &msg_unpack(msg_buffer.data)->struct_data;
                MsgString *event_type = &msg_struct_data(event, "type")->string_data;

                if (strcmp(event_type->data, "launch") == 0)
                {
                    MsgString *msg_executable = &msg_struct_data(event, "executable")->string_data;
                    MsgArray *msg_arguments = &msg_struct_data(event, "arguments")->array_data;
                    MsgString *msg_working_dir = &msg_struct_data(event, "working_dir")->string_data;
                    MsgArray *msg_environments = &msg_struct_data(event, "environments")->array_data;

                    SBTarget target = debugger.CreateTarget(msg_executable->data);

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
                    SBProcess process = target.Launch(listener, (const char **)arguments, (const char **)environments, 
                            nullptr, nullptr, nullptr, msg_working_dir->data, 0, false, error);
                    break;
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

    pthread_join(response_thread, nullptr);
}

