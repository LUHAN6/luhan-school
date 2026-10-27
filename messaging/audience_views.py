from django.contrib.auth.decorators import login_required
from django.shortcuts import render

AUDIENCES = [
    {
        "key": "parents",
        "title": "All Parents",
        "icon": "👨‍👩‍👧",
        "description": "School announcements, fee reminders, meetings and parent notices.",
    },
    {
        "key": "students",
        "title": "All Students",
        "icon": "🎓",
        "description": "Examination timetables, learning notices and student announcements.",
    },
    {
        "key": "staff",
        "title": "All Staff",
        "icon": "👩‍🏫",
        "description": "Staff meetings, duty schedules and internal circulars.",
    },
    {
        "key": "individual",
        "title": "Individual Person",
        "icon": "👤",
        "description": "Choose one specific parent, student or staff member.",
    },
    {
        "key": "everyone",
        "title": "All (Everyone)",
        "icon": "📢",
        "description": "School-wide announcements for parents, students and staff.",
    },
]


@login_required
def audience_dashboard(request):
    selected_key = request.GET.get("audience", "")
    valid_keys = {item["key"] for item in AUDIENCES}
    if selected_key not in valid_keys:
        selected_key = ""

    selected = next(
        (item for item in AUDIENCES if item["key"] == selected_key),
        None,
    )

    return render(
        request,
        "messaging/audience_dashboard.html",
        {
            "audiences": AUDIENCES,
            "selected_audience": selected,
        },
    )
