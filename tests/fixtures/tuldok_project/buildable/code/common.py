"""Hooks the tests use to make a stand-in command fail, stall, pause or leave out its output.

Each BUILDABLE_* variable names the scripts it applies to, separated by commas.
"""
import os
import sys
import time


def _named(variable, script):
    return script in os.environ.get(variable, '').split(',')


def before(script):
    """Run the hooks that act before a script does its work."""
    if _named('BUILDABLE_FAIL', script):
        print(f'{script}: failing as asked', file=sys.stderr)
        sys.exit(3)
    if _named('BUILDABLE_STALL', script):
        time.sleep(60)
    hold = os.environ.get('BUILDABLE_HOLD', '')
    if hold.startswith(script + ':'):
        directory = hold[len(script) + 1:]
        open(os.path.join(directory, 'started'), 'w').close()
        deadline = time.monotonic() + 30
        while not os.path.exists(os.path.join(directory, 'release')) and time.monotonic() < deadline:
            time.sleep(0.05)


def skip_output(script):
    return _named('BUILDABLE_SKIP_OUTPUT', script)
