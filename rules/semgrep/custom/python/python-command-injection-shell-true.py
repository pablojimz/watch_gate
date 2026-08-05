import subprocess
import os


def bad1(user_input):
    # ruleid: python-command-injection-shell-true
    subprocess.run(f"ls {user_input}", shell=True)


def bad2(user_input):
    # ruleid: python-command-injection-shell-true
    subprocess.call("ls " + user_input, shell=True)


def bad3(user_input):
    # ruleid: python-command-injection-shell-true
    os.system(user_input)


def bad4(user_input):
    # ruleid: python-command-injection-shell-true
    os.popen(user_input)


def ok1():
    # ok: python-command-injection-shell-true
    subprocess.run("ls -la", shell=True)


def ok2():
    # ok: python-command-injection-shell-true
    os.system("uptime")


def ok3(user_dir):
    # ok: python-command-injection-shell-true
    subprocess.run(["ls", user_dir])
