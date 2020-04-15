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
    for (int i = 0; i < 100; i++)
    {
        printf("Hello %d\n", i);
    }
}

