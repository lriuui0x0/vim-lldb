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

int f()
{
    int vec = 10;
    return 10;
}

int main()
{
    Vec2 vec;
    vec.x = 0;
    vec.inner.y = 100;
    f();
    return 0;
}

