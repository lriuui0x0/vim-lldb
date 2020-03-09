#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>

struct MsgObject;

typedef int64_t MsgInt;

struct MsgString
{
    MsgInt length;
    char *data;
};

struct MsgArray
{
    MsgInt length;
    MsgObject *data;
};

struct MsgStruct
{
    MsgInt length;
    MsgString *keys;
    MsgObject *data;
};

enum struct MsgObjectType : MsgInt
{
    msg_int,
    msg_string,
    msg_array,
    msg_struct,
};

struct MsgObject
{
    MsgObjectType type;
    union
    {
        MsgInt int_data;
        MsgString string_data;
        MsgArray array_data;
        MsgStruct struct_data;
    };
};

MsgObject *msg_struct_data(MsgStruct *struct_data, char *string)
{
    for (MsgInt i = 0; i < struct_data->length; i++)
    {
        if (strcmp(struct_data->keys[i].data, string) == 0)
        {
            return struct_data->data + i;
        }
    }
    return nullptr;
}

struct MsgBuffer
{
    char *data;
    MsgInt capacity;
    MsgInt length;
};

MsgBuffer msg_buffer_create()
{
    MsgBuffer buffer;
    buffer.capacity = 4096;
    buffer.length = 0;
    buffer.data = (char *)malloc(sizeof(char) * buffer.capacity);
    return buffer;
}

void msg_buffer_reserve(MsgBuffer *buffer, MsgInt length)
{
    if (buffer->length + length > buffer->capacity)
    {
        buffer->capacity *= 2;
        buffer->data = (char *)realloc(buffer->data, sizeof(char) * buffer->capacity);
    }
}

void msg_buffer_reset(MsgBuffer *buffer)
{
    buffer->length = 0;
}

void msg_pack_int(MsgBuffer *buffer, MsgInt int_data)
{
    msg_buffer_reserve(buffer, sizeof(MsgObjectType) + sizeof(MsgInt));

    *(MsgObjectType *)(buffer->data + buffer->length) = MsgObjectType::msg_int;
    buffer->length += sizeof(MsgObjectType);

    *(MsgInt *)(buffer->data + buffer->length) = int_data;
    buffer->length += sizeof(MsgInt);
}

void msg_pack_string(MsgBuffer *buffer, char *string_data, MsgInt string_length)
{
    msg_buffer_reserve(buffer, sizeof(MsgObjectType) + sizeof(MsgInt) + sizeof(char) * string_length);

    *(MsgObjectType *)(buffer->data + buffer->length) = MsgObjectType::msg_string;
    buffer->length += sizeof(MsgObjectType);

    *(MsgInt *)(buffer->data + buffer->length) = string_length;
    buffer->length += sizeof(MsgInt);

    memcpy(buffer->data + buffer->length, string_data, sizeof(char) * string_length);
    buffer->length += sizeof(char) * string_length;
}

void msg_pack_array(MsgBuffer *buffer, MsgInt array_length)
{
    msg_buffer_reserve(buffer, sizeof(MsgObjectType) + sizeof(MsgInt));

    *(MsgObjectType *)(buffer->data + buffer->length) = MsgObjectType::msg_array;
    buffer->length += sizeof(MsgObjectType);

    *(MsgInt *)(buffer->data + buffer->length) = array_length;
    buffer->length += sizeof(MsgInt);
}

void msg_pack_struct(MsgBuffer *buffer, MsgInt struct_length)
{
    msg_buffer_reserve(buffer, sizeof(MsgObjectType) + sizeof(MsgInt));

    *(MsgObjectType *)(buffer->data + buffer->length) = MsgObjectType::msg_struct;
    buffer->length += sizeof(MsgObjectType);

    *(MsgInt *)(buffer->data + buffer->length) = struct_length;
    buffer->length += sizeof(MsgInt);
}

void msg_pack_key(MsgBuffer *buffer, char *string_data, MsgInt string_length)
{
    msg_buffer_reserve(buffer, sizeof(MsgInt) + sizeof(char) * string_length);

    *(MsgInt *)(buffer->data + buffer->length) = string_length;
    buffer->length += sizeof(MsgInt);

    memcpy(buffer->data + buffer->length, string_data, sizeof(char) * string_length);
    buffer->length += sizeof(char) * string_length;
}

char *msg_unpack_string(char *raw_data, MsgString *string)
{
    string->length = *(MsgInt *)raw_data;
    raw_data += sizeof(MsgInt);

    string->data = (char *)malloc(sizeof(char) * (string->length + 1));
    memcpy(string->data, raw_data, string->length);
    string->data[string->length] = 0;
    raw_data += sizeof(char) * string->length;

    return raw_data;
}

char *msg_unpack(char *raw_data, MsgObject *object)
{
    object->type = *(MsgObjectType *)raw_data;
    raw_data += sizeof(MsgObjectType);

    switch (object->type)
    {
    case MsgObjectType::msg_int:
        {
            object->int_data = *(MsgInt *)raw_data;
            raw_data += sizeof(MsgInt);
        }
        break;

    case MsgObjectType::msg_string:
        {
            raw_data = msg_unpack_string(raw_data, &object->string_data);
        }
        break;

    case MsgObjectType::msg_array:
        {
            object->array_data.length = *(MsgInt *)raw_data;
            raw_data += sizeof(MsgInt);

            object->array_data.data = (MsgObject *)malloc(sizeof(MsgObject) * object->array_data.length);
            for (MsgInt i = 0; i < object->array_data.length; i++)
            {
                raw_data = msg_unpack(raw_data, object->array_data.data + i);
            }
        }
        break;

    case MsgObjectType::msg_struct:
        {
            object->struct_data.length = *(MsgInt *)raw_data;
            raw_data += sizeof(MsgInt);

            object->struct_data.keys = (MsgString *)malloc(sizeof(MsgString) * object->struct_data.length);
            object->struct_data.data = (MsgObject *)malloc(sizeof(MsgObject) * object->struct_data.length);
            for (MsgInt i = 0; i < object->struct_data.length; i++)
            {
                raw_data = msg_unpack_string(raw_data, object->struct_data.keys + i);
            }
            for (MsgInt i = 0; i < object->struct_data.length; i++)
            {
                raw_data = msg_unpack(raw_data, object->struct_data.data + i);
            }
        }
        break;
    }

    return raw_data;
}

MsgObject *msg_unpack(char *raw_data)
{
    MsgObject *object = (MsgObject *)malloc(sizeof(MsgObject));
    msg_unpack(raw_data, object);
    return object;
}

