# coding: utf-8
from __future__ import absolute_import

from celery import shared_task

from services import new_sms


@shared_task
def create_sms(recipient, message, inbox, device_id):
    return new_sms(
        recipient,
        message,
        inbox,
        device_id
    )
