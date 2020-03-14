/*
1) launch process (command line argument, environment variable, working directory)
2) step over/in/out
3) breakpoint toggle (line, function) 4) watch variable, navigate struct, array
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
    Array<char> msg_buffer = create_array<char>(4096);
    while (true)
    {
        SBEvent event;
        SBStream event_stream;
        if (listener->WaitForEvent(1, event))
        {
            event.GetDescription(event_stream);
            char *data = (char *)event_stream.GetData();

            array_reset(&msg_buffer);
            msg_pack_struct(&msg_buffer, 1);

            msg_pack_key(&msg_buffer, "event", strlen("event"));
            msg_pack_string(&msg_buffer, data, strlen(data));

            MsgInt msg_length = msg_buffer.length;
            int byte_written = write(STDOUT_FILENO, &msg_length, sizeof(MsgInt));
            if (byte_written == sizeof(MsgInt))
            {
                byte_written = write(STDOUT_FILENO, msg_buffer.data, msg_length);
                if (byte_written == sizeof(msg_length))
                {
                }
            }
        }
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

