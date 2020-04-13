#include <cstdio>

struct Vec2Inner
{
    int x;
    int y;
};

struct Vec2
{
    int x;
    int y;
    Vec2Inner inner;
};

struct Vec2Another
{
    Vec2 inner;
};

int f()
{
    int x;
    return 10;
}

int main()
{
    char* hello = "HellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHellHelloooooooooooooooooooooooooooooooooooooooooooooooooooooooooooHello"
    int buffer[20];
    int *x = buffer;
    Vec2 vec;
    vec.x = 0;
    vec.inner.y = 100;
    Vec2 *pvec = &vec;
    f();
    while (true)  ;
    return 0;
}

