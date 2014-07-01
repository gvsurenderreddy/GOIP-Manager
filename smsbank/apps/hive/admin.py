# coding: utf-8
from django.contrib import admin
from models import (
    Device,
    DeviceList,
    CallForwarding,
    Sms
)
from smsbank.apps.hive.client import GOIPClient, DaemonClient


class DeviceAdmin(admin.ModelAdmin):
    actions = [
        'reboot',
        'shutdown',
        'terminate',
        'restart'
    ]

    def reboot(self, request, queryset):
        """Reboot selected GOIP devices"""
        for device in queryset:
            GOIPClient(device.device_id).goip_restart()

    reboot.short_description = u'Перезагрузить устройствa'

    def shutdown(self, request, queryset):
        """Shutdown selected GOIP devices"""
        for device in queryset:
            GOIPClient(device.device_id).goip_shutdown()

    shutdown.short_description = u'Выключить устройства'

    def terminate(self, request, queryset):
        """Terminate daemon itself"""
        DaemonClient().terminate()

    terminate.short_description = u'Завершить демона'

    def restart(self, request, queryset):
        """Restart daemon itself"""
        DaemonClient().restart()

    restart.short_description = u'Перезапустить демона'

admin.site.register(Device, DeviceAdmin)
admin.site.register([Sms, DeviceList, CallForwarding])
