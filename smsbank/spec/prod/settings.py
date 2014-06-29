# -*- coding: utf-8 -*-
from smsbank.settings import *

WSGI_APPLICATION = 'smsbank.spec.prod.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'simhosting',
        'USER': 'simhosting',
        'PASSWORD': 'gielei0M',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
