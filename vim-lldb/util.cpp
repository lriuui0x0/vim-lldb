#include <cstring>

template <typename T>
struct Array
{
    T *data;
    int capacity;
    int length;
};

template <typename T>
Array<T> create_array(int capacity)
{
    Array<T> array;
    array.capacity = capacity;
    array.length = 0;
    array.data = (T *)malloc(sizeof(T) * array.capacity);
    return array;
}

template <typename T>
void array_reserve(Array<T> *array, int length)
{
    if (array->length + length > array->capacity)
    {
        array->capacity *= 2;
        array->data = (T *)realloc(array->data, sizeof(T) * array->capacity);
    }
}

template <typename T>
void array_push(Array<T> *array, T data)
{
    array_reserve(array, 1);
    array->data[array->length++] = data;
}

