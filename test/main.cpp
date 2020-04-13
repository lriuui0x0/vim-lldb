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
    Vec2Another vec;
    return 10;
}

int main()
{
    Vec2 vec;
    vec.x = 0;
    vec.inner.y = 100;
    f();
    while (true)  ;
    return 0;
}

