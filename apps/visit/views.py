import os

import requests

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from zhuartcc.overrides import send_mail
from .models import Visit
from ..administration.models import ActionLog
from ..user.models import User
from ..user.updater import assign_oper_init
from zhuartcc.decorators import require_session, require_staff


# Serves 'visit.html' file. Saves request from form data on POST
@require_session
def submit_visiting_request(request):
    if request.method == 'POST':
        if User.objects.filter(cid=request.POST.get('cid')).exclude(status=2).exists():
            return HttpResponse('You are already a controller at PCF!', status=403)
        else:
            visiting_request = Visit(
                cid=int(request.POST.get('cid')),
                rating=request.POST.get('rating'),
                home_facility=request.POST.get('home_facility'),
                first_name=request.POST.get('first_name'),
                last_name=request.POST.get('last_name'),
                email=request.POST.get('email'),
                reason=request.POST.get('reason'),
                submitted=timezone.now(),
            )
            visiting_request.save()

            send_mail(
                'We have received your visiting request!',
                render_to_string('emails/visiting_request_received.html', {'name': visiting_request.first_name}),
                os.getenv('NO_REPLY'),
                [visiting_request.email],
            )

            return redirect(reverse('home'))

    return render(request, 'visit.html', {'page_title': 'Visit PCF'})

@require_staff
def submit_man_visiting_request(request):
    if request.method == 'POST':
        if User.objects.filter(cid=request.POST.get('cid')).exclude(status=2).exists():
            return HttpResponse('User is already a controller at PCF!', status=403)
        else:
            visiting_request = Visit(
                cid=int(request.POST.get('cid')),
                rating=request.POST.get('rating'),
                home_facility=request.POST.get('home_facility'),
                first_name=request.POST.get('first_name'),
                last_name=request.POST.get('last_name'),
                email=request.POST.get('email'),
                reason=request.POST.get('reason'),
                submitted=timezone.now(),
            )
            visiting_request.save()

            return redirect(reverse('home'))

    return render(request, 'add_visitor.html', {'page_title': 'Manual Add Visitor'})



# Gets all visiting requests from local database and serves 'visiting_requests.html' file
@require_staff
def view_visiting_requests(request):
    visiting_requests = Visit.objects.all()
    return render(request, 'visiting_requests.html', {
        'page_title': 'Visiting Requests',
        'visiting_requests': visiting_requests
    })


# Creates User object from visiting request with CID specified in POST
@require_staff
@require_POST
def accept_visiting_request(request, visit_id):
    visiting_request = Visit.objects.get(id=visit_id)

    # If user is visiting the ARTCC after being marked inactive
    if User.objects.filter(cid=visiting_request.cid).exists():
        edit_user = User.objects.get(cid=visiting_request.cid)
        if edit_user.status == 2:
            edit_user.status = 0
            edit_user.email = visiting_request.email
            edit_user.oper_init = assign_oper_init(visiting_request.first_name[0], visiting_request.first_name[0])
            edit_user.rating = visiting_request.rating
            edit_user.main_role = 'VC'
            edit_user.assign_initial_cert()
            requests.post(
                f'https://api.vatusa.net/v2/facility/{os.getenv("ARTCC_ICAO")}/roster/manageVisitor/{visiting_request.cid}',
                params={'apikey': os.getenv('API_KEY')}
            )
            edit_user.save()
        else:
            return HttpResponse('Visitor is already on the roster.', status=400)
    else:
        visiting_request.add_to_roster()
        requests.post(
            f'https://api.vatusa.net/v2/facility/{os.getenv("ARTCC_ICAO")}/roster/manageVisitor/{visiting_request.cid}',
            params={'apikey': os.getenv('API_KEY')}
        )


    ActionLog(action=f'{visiting_request}\'s visiting request was accepted by {request.user_obj}.').save()

    send_mail(
        'Welcome to Pacific Control Facility!',
        render_to_string('emails/visiting_request_accepted.html', {'name': visiting_request.first_name}),
        os.getenv('NO_REPLY'),
        [visiting_request.email],
    )

    visiting_request.delete()
    return HttpResponse(status=200)


# Deletes visiting request with CID specified in POST
@require_staff
@require_POST
def reject_visiting_request(request, visit_id):
    visiting_request = Visit.objects.get(id=visit_id)

    ActionLog(action=f'{visiting_request}\'s visiting request was rejected by {request.user_obj}.').save()

    context = {
        'name': visiting_request.first_name,
        'reason': request.POST.get('reason')
    }
    send_mail(
        'Your Pacific Control Facility Visiting Request...',
        render_to_string('emails/visiting_request_rejected.html', context),
        os.getenv('NO_REPLY'),
        [visiting_request.email],
    )

    visiting_request.delete()
    return redirect(reverse('visit_requests'))
