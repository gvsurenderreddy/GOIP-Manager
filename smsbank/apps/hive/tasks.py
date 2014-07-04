# coding: utf-8
from __future__ import absolute_import

from celery import shared_task

from services import new_sms, initialize_device


@shared_task
def create_sms(recipient, message, inbox, device_id):
    print 'New SMS! %s:%s' % (recipient, message)
    return new_sms(
        recipient,
        message,
        inbox,
        device_id
    )


@shared_task
def auth_device(device_id, host, port):
    print 'Authorizing device! [%s]%s:%s' % (device_id, host, port)
    initialize_device(device_id, host, port)
