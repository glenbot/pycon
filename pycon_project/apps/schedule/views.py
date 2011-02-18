import datetime
import itertools

from django.conf import settings
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext

from django.contrib.auth.decorators import login_required

from schedule.forms import PlenaryForm, RecessForm, PresentationForm
from schedule.models import Slot, Presentation, Track, Session, SessionRole


wed_morn_start = datetime.datetime(2011, 3, 9, 9, 0)  # 9AM Eastern
wed_morn_end = datetime.datetime(2011, 3, 9, 12, 20)  # 12:20PM Eastern
wed_after_start = datetime.datetime(2011, 3, 9, 14, 0)  # 2PM Eastern
wed_after_end = datetime.datetime(2011, 3, 9, 16, 40)  # 4:40PM Eastern
thu_morn_start = datetime.datetime(2011, 3, 10, 9, 0)  # 9AM Eastern
thu_morn_end = datetime.datetime(2011, 3, 10, 12, 20)  # 12:20PM Eastern
thu_after_start = datetime.datetime(2011, 3, 10, 14, 0)  # 2PM Eastern
thu_after_end = datetime.datetime(2011, 3, 10, 16, 40)  # 4:40PM Eastern

WEDNESDAY_MORNING = (wed_morn_start, wed_morn_end)
WEDNESDAY_AFTERNOON = (wed_after_start, wed_after_end)
THURSDAY_MORNING = (thu_morn_start, thu_morn_end)
THURSDAY_AFTERNOON = (thu_after_start, thu_after_end)


def schedule_list(request, template_name="schedule/schedule_list.html", extra_context=None):
    
    if extra_context is None:
        extra_context = {}
    
    slots = Slot.objects.all().order_by("start")
    
    return render_to_response(template_name, dict({
        "slots": slots,
        "timezone": settings.SCHEDULE_TIMEZONE,
    }, **extra_context), context_instance=RequestContext(request))


def schedule_presentation(request, presentation_id, template_name="schedule/presentation_detail.html", extra_context=None):
    
    if extra_context is None:
        extra_context = {}
    
    presentation = get_object_or_404(Presentation, id=presentation_id)
    
    return render_to_response(template_name, dict({
        "presentation": presentation,
        "timezone": settings.SCHEDULE_TIMEZONE,
    }, **extra_context), context_instance=RequestContext(request))


def schedule_list_talks(request):
    
    talks = Presentation.objects.filter(
        presentation_type__in=[Presentation.PRESENTATION_TYPE_PANEL, Presentation.PRESENTATION_TYPE_TALK]
    )
    talks = talks.order_by("pk")
    
    return render_to_response("schedule/list_talks.html", dict({
        "talks": talks,
    }), context_instance=RequestContext(request))


def schedule_list_talks_expanded(request):
    
    talks = Presentation.objects.filter(
        presentation_type__in=[Presentation.PRESENTATION_TYPE_TALK]
    )
    talks = talks.order_by("pk")

    panels = Presentation.objects.filter(
        presentation_type__in=[Presentation.PRESENTATION_TYPE_PANEL]
    )
    panels = panels.order_by("pk")
    
    return render_to_response("schedule/list_talks_expanded.html", dict({
        "talks": talks,
        "panels": panels
    }), context_instance=RequestContext(request))


def schedule_list_tutorials(request):
    
    tutorials = Presentation.objects.filter(
        presentation_type=Presentation.PRESENTATION_TYPE_TUTORIAL
    )
    tutorials = tutorials.order_by("pk")
    
    return render_to_response("schedule/list_tutorials.html", dict({
        "tutorials": tutorials,
    }), context_instance=RequestContext(request))


def schedule_list_posters(request):
    
    posters = Presentation.objects.filter(
        presentation_type=Presentation.PRESENTATION_TYPE_POSTER
    )
    posters = posters.order_by("pk")
    
    return render_to_response("schedule/list_posters.html", dict({
        "posters": posters,
    }), context_instance=RequestContext(request))


def schedule_tutorials(request):
    
    tutorials = {
        "wed": {
            "morning": {
                "slot": WEDNESDAY_MORNING,
                "presentations": Presentation.objects.filter(
                    slot__start=WEDNESDAY_MORNING[0]
                ).order_by("pk"),
            },
            "afternoon": {
                "slot": WEDNESDAY_AFTERNOON,
                "presentations": Presentation.objects.filter(
                    slot__start=WEDNESDAY_AFTERNOON[0]
                ).order_by("pk"),
            }
        },
        "thurs": {
            "morning": {
                "slot": THURSDAY_MORNING,
                "presentations": Presentation.objects.filter(
                    slot__start=THURSDAY_MORNING[0]
                ).order_by("pk"),
            },
            "afternoon": {
                "slot": THURSDAY_AFTERNOON,
                "presentations": Presentation.objects.filter(
                    slot__start=THURSDAY_AFTERNOON[0]
                ).order_by("pk"),
            }
        }
    }
    
    ctx = {
        "tutorials": tutorials,
    }
    ctx = RequestContext(request, ctx)
    return render_to_response("schedule/tutorials.html", ctx)


class Timetable(object):
    
    def __init__(self, slots):
        self.slots = slots
    
    @property
    def tracks(self):
        return Track.objects.filter(
            pk__in = self.slots.exclude(track=None).values_list("track", flat=True).distinct()
        ).order_by("name")
    
    def __iter__(self):
        times = sorted(set(itertools.chain(*self.slots.values_list("start", "end"))))
        slots = list(self.slots.order_by("start", "track__name"))
        row = []
        for time in times:
            row = {"time": time, "slots": []}
            for slot in slots:
                if slot.start == time:
                    slot.rowspan = Timetable.rowspan(times, slot.start, slot.end)
                    row["slots"].append(slot)
            if len(row["slots"]) == 1:
                row["colspan"] = len(self.tracks)
            else:
                row["colspan"] = 1
            yield row
    
    @staticmethod
    def rowspan(times, start, end):
        return times.index(end) - times.index(start)


@login_required
def schedule_conference_edit(request):
    if not request.user.is_staff:
        return redirect("/")
    ctx = {
        "friday": Timetable(Slot.objects.filter(start__week_day=6)),
        "saturday": Timetable(Slot.objects.filter(start__week_day=7)),
        "sunday": Timetable(Slot.objects.filter(start__week_day=1)),
    }
    ctx = RequestContext(request, ctx)
    return render_to_response("schedule/conference_edit.html", ctx)


@login_required
def schedule_slot_add(request, slot_id, kind):
    
    if not request.user.is_staff:
        return redirect("/")
    
    slot = Slot.objects.get(pk=slot_id)
    
    form_class = {
        "plenary": PlenaryForm,
        "break": RecessForm,
        "presentation": PresentationForm,
    }[kind]
    
    if request.method == "POST":
        form = form_class(request.POST)
        
        if form.is_valid():
            slot_content = form.save(commit=False)
            slot.assign(slot_content)
            return redirect("schedule_conference_edit")
    else:
        form = form_class()
    
    ctx = {
        "slot": slot,
        "kind": kind,
        "form": form,
        "add": True,
    }
    ctx = RequestContext(request, ctx)
    return render_to_response("schedule/slot_place.html", ctx)


@login_required
def schedule_slot_edit(request, slot_id):
    
    if not request.user.is_staff:
        return redirect("/")
    
    slot = Slot.objects.get(pk=slot_id)
    kind = slot.kind.name
    
    form_tuple = {
        "plenary": (PlenaryForm, {"instance": slot.content()}),
        "recess": (RecessForm, {"instance": slot.content()}),
        "presentation": (PresentationForm, {"initial": {"presentation": slot.content()}}),
    }[kind]
    
    if request.method == "POST":
        form = form_tuple[0](request.POST, **form_tuple[1])
        
        if form.is_valid():
            slot_content = form.save(commit=False)
            slot.assign(slot_content, old_content=slot.content())
            return redirect("schedule_conference_edit")
    else:
        form = form_tuple[0](**form_tuple[1])
    
    ctx = {
        "slot": slot,
        "kind": kind,
        "form": form,
        "add": False,
    }
    ctx = RequestContext(request, ctx)
    return render_to_response("schedule/slot_place.html", ctx)


@login_required
def schedule_slot_remove(request, slot_id):
    
    if not request.user.is_staff:
        return redirect("/")
    
    slot = Slot.objects.get(pk=slot_id)
    
    if request.method == "POST":
        slot.unassign()
        return redirect("schedule_conference_edit")
    
    ctx = {
        "slot": slot,
    }
    ctx = RequestContext(request, ctx)
    return render_to_response("schedule/slot_remove.html", ctx)


def track_list(request):
    
    tracks = Track.objects.order_by("name")
    
    return render_to_response("schedule/track_list.html", {
        "tracks": tracks,
    }, context_instance=RequestContext(request))


def track_detail(request, track_id):
    
    track = get_object_or_404(Track, id=track_id)
    
    return render_to_response("schedule/track_detail.html", {
        "track": track,
    }, context_instance=RequestContext(request))


def track_detail_none(request):
    
    sessions = Session.objects.filter(track=None)
    slots = Slot.objects.filter(track=None)
    
    return render_to_response("schedule/track_detail_none.html", {
        "sessions": sessions,
        "slots": slots,
    }, context_instance=RequestContext(request))


def session_list(request):
    
    sessions = Session.objects.all()
    
    return render_to_response("schedule/session_list.html", {
        "sessions": sessions,
    }, context_instance=RequestContext(request))


def session_detail(request, session_id):
    
    session = get_object_or_404(Session, id=session_id)
    
    chair = None
    chair_denied = False
    chairs = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_CHAIR).exclude(status=False)
    if chairs:
        chair = chairs[0].user
    else:
        if request.user.is_authenticated():
            # did the current user previously try to apply and got rejected?
            if SessionRole.objects.filter(session=session, user=request.user, role=SessionRole.SESSION_ROLE_CHAIR, status=False):
                chair_denied = True
    
    runner = None
    runner_denied = False
    runners = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_RUNNER).exclude(status=False)
    if runners:
        runner = runners[0].user
    else:
        if request.user.is_authenticated():
            # did the current user previously try to apply and got rejected?
            if SessionRole.objects.filter(session=session, user=request.user, role=SessionRole.SESSION_ROLE_RUNNER, status=False):
                runner_denied = True
    
    if request.method == "POST" and request.user.is_authenticated():
        role = request.POST.get("role")
        if role == "chair":
            if chair == None and not chair_denied:
                SessionRole(session=session, role=SessionRole.SESSION_ROLE_CHAIR, user=request.user).save()
        elif role == "runner":
            if runner == None and not runner_denied:
                SessionRole(session=session, role=SessionRole.SESSION_ROLE_RUNNER, user=request.user).save()
        elif role == "un-chair":
            if chair == request.user:
                session_role = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_CHAIR, user=request.user)
                if session_role:
                    session_role[0].delete()
        elif role == "un-runner":
            if runner == request.user:
                session_role = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_RUNNER, user=request.user)
                if session_role:
                    session_role[0].delete()
        
        return redirect("schedule_session_detail", session_id)
    
    return render_to_response("schedule/session_detail.html", {
        "session": session,
        "chair": chair,
        "chair_denied": chair_denied,
        "runner": runner,
        "runner_denied": runner_denied,
    }, context_instance=RequestContext(request))