#!/usr/bin/env python
from fabric.api import local


def build():
    """Build static assets and commit"""
    local('cd etc && ./node_modules/.bin/grunt build')
    local('./manage.py collectstatic')


def commit():
    """Commit new changes"""
    local('git add -p && git commit')


def push():
    """Push to private repo"""
    local('git push shido.github')
