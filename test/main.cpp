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
    int z;
    return 10;
}

int main(int argc, char **argv)
{
    int x[3] = { 1, 2, 3 };
    int *y = x;
    f();
    return 0;
}

