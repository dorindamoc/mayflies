#!/bin/sh
set -e
python setup.py --init
exec python scheduler.py "$@"
