# coding: utf-8
from __future__ import absolute_import

from celery import shared_task

from smsbank.apps.hive.services import new_sms, initialize_device


@shared_task
def create_sms(recipient, message, inbox, device_id):
    create_sms.get_logger().info(
        'New SMS! [device:%s]%s:%s' % (device_id, recipient, message)
    )
    new_sms(
        recipient,
        message,
        inbox,
        device_id
    )


@shared_task
def auth_device(device_id, host, port):
    auth_device.get_logger().info(
        'Authorizing device! [device:%s]%s:%s' % (device_id, host, port)
    )
    initialize_device(device_id, host, port)
