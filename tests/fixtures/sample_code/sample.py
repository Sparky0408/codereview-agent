import math  # noqa: F401


class Calculator:
    def __init__(self):
        self.value = 0

def add(a: int, b: int) -> int:
    return a + b

def complex_function(items: list[int]) -> int:
    total = 0
    for item in items:
        if item > 0:
            total += item
        elif item == 0:
            continue
        else:
            if item == -1:
                total -= 1
            else:
                total -= item
    while total > 100:
        total -= 10
    return total
