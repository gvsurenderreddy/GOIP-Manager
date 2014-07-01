# coding: utf-8
from django.contrib import admin
from models import (
    Device,
    DeviceList,
    CallForwarding,
    Sms
)
from smsbank.apps.hive.client import GOIPClient


class DeviceAdmin(admin.ModelAdmin):
    actions = ['reboot', 'shutdown']

    def reboot(self, request, queryset):
        for device in queryset:
            GOIPClient(device.device_id).goip_restart()

    reboot.short_description = u'Перезагрузить устройствa'

    def shutdown(self, request, queryset):
        for device in queryset:
            GOIPClient(device.device_id).goip_shutdown()

    shutdown.short_description = u'Выключить устройства'


admin.site.register(Device, DeviceAdmin)
admin.site.register([Sms, DeviceList, CallForwarding])
