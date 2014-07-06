# coding: utf-8

# Django modules
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.http import Http404
from django.contrib.auth import(
    login as login_user,
    logout as logout_user,
    authenticate
)

# External modules
import redis

# Project modules
from forms import (
    SMSForm,
    CustomAuthForm,
    CustomRegisterForm,
    CallForwardingForm
)
from models import (
    DeviceList,
    Device,
    CallForwarding
)
from services import (
    associate_profiles,
    new_call_forwarding_profile,
    list_sms,
    delete_sms,
    get_device_by_id
)
from client import GOIPClient

################
# Landing page #
################


def index(request):
    """Display landing page"""
    if request.user.is_authenticated():
        return redirect('grunts')

    return render(request, 'home.html')


def login(request):
    """Login existing user and redirect to device list page"""

    if request.user.is_authenticated():
        return redirect('grunts')

    if request.method == 'POST':
        form = CustomAuthForm(data=request.POST)
        if not form.is_valid():
            return render(
                request,
                'auth/login.html',
                {'form': form}
            )

        # If form is valid, try to authenticate user
        user = authenticate(
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password']
        )

        if user is not None:
            # Log in and redirect to device list
            login_user(request, user)
            return redirect('grunts')
        else:
            return render(
                request,
                'auth/login.html',
                {'form': form}
            )
    else:
        form = CustomAuthForm()

    return render(request, 'auth/login.html', {'form': form})


def register(request):
    """Try to register new user"""

    if request.user.is_authenticated():
        return redirect('grunts')

    if request.method == 'POST':
        form = CustomRegisterForm(data=request.POST)
        if not form.is_valid():
            return render(
                request,
                'auth/register.html',
                {'form': form}
            )
        else:
            # If valid form -> create user
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )

            # And associate all required profiles
            associate_profiles(user)

            # Login registered user
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login_user(request, user)

            # Go to device list
            return redirect('grunts')
    else:
        form = CustomRegisterForm()

    return render(request, 'auth/register.html', {'form': form})

#####################
# Working with hive #
#####################


def grunts(request):
    """Display device list"""

    if not request.user.is_authenticated():
        return redirect('login')

    # Switch display groups if required
    groups = Device.objects.values_list('ip', flat=True).distinct()
    if request.method == 'POST':
        group = request.POST.get('group')
    else:
        group = None

    # Get device list available for this user
    try:
        device_list = request.user.device_list.get()
        if group:
            devices = device_list.devices.filter(
                ip=group
            ).order_by('device_id')
        else:
            devices = device_list.devices.all().order_by('device_id')

    # If admin, get all devices
    except DeviceList.DoesNotExist:
        if group:
            devices = Device.objects.filter(
                ip=group
            ).order_by('device_id')
        else:
            devices = Device.objects.all().order_by('device_id')

    # Update status for each of the device
    r = redis.StrictRedis()
    for device in devices:
        try:
            status = r.get(device.device_id)
            if status:
                device.online = True if status == 'LOGIN' else False
                device.save()
        except redis.ConnectionError:
            pass

    # Additional sort, due to alphanumeric device_id
    devices = sorted(
        devices,
        key=lambda d: int(d.device_id) if d.device_id
        and d.device_id.isdigit() else None
    )

    # Sort by status
    devices = sorted(
        devices,
        key=lambda d: not d.online
    )

    return render(request, 'devices/grunts.html', {
        'grunts': devices,
        'groups': groups,
        'active': group
    })


def grunt_list(request, grunt, inbox):
    """Display device sms list and controls"""

    if not request.user.is_authenticated():
        return redirect('index')

    device = get_device_by_id(grunt)
    if not device:
        raise Http404

    # Delete SMS if post
    sms_deleted = False
    if request.method == 'POST':
        delete_sms(request.POST.get('sms_to_delete'))
        sms_deleted = True

    # Get sms list
    sms_list = list_sms(device, inbox)

    return render(request, 'devices/grunt.html', {
        'grunt': device,
        'sms_list': sms_list,
        'inbox': inbox,
        'sms_deleted': sms_deleted
    })


def grunt_send(request, grunt):
    """Send SMS via specified grunt"""

    if not request.user.is_authenticated():
        return redirect('index')

    sms_sent = False
    error_message = False

    if request.method == 'POST':
        form = SMSForm(data=request.POST)
        if form.is_valid():
            # Get devid as specified in GOIP
            device = get_device_by_id(grunt)
            # Send SMS
            if device:
                client = GOIPClient(device.device_id)
                sms_sent = client.send_sms(
                    form.cleaned_data['phone'],
                    form.cleaned_data['message']
                )
            else:
                error_message = u'Не удалось получить GOIP id устройства'
        else:
            error_message = u'Указаны неверные данные'
    else:
        form = SMSForm()

    return render(request, 'devices/sms-send.html', {
        'grunt': grunt,
        'form': form,
        'sms_sent': sms_sent,
        'error_message': error_message,
    })


def logout(request):
    """Try to logout existing user"""
    if request.user.is_authenticated():
        logout_user(request)
        return redirect('index')


##############
# Additional #
##############

def profile(request):
    """Display configuration associated with user account"""
    if not request.user.is_authenticated():
        return redirect('login')

    profile_updated = False
    error_message = False

    # Get or create profile
    try:
        profile = request.user.call_forwarding.get()
    except CallForwarding.DoesNotExist:
        profile = new_call_forwarding_profile(request.user)

    if request.method == 'POST':
        form = CallForwardingForm(data=request.POST, instance=profile)
        if form.is_valid():
            form.save()
            profile_updated = True
        else:
            error_message = u'Не все поля заполнены как надо!'
    else:
        form = CallForwardingForm(instance=profile)

    return render(request, 'profile/main.html', {
        'form': form,
        'profile_updated': profile_updated,
        'error_message': error_message
    })

##############
# Additional #
##############


def info(request):
    """Display application info"""
    return render(request, 'about.html')
