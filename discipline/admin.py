from django.contrib import admin
from .models import *

class StatementInline(admin.TabularInline):
    model = DisciplineStatement
    extra = 0
class ActionInline(admin.TabularInline):
    model = DisciplineAction
    extra = 0
class MeetingInline(admin.TabularInline):
    model = DisciplineMeeting
    extra = 0

@admin.register(DisciplineCase)
class DisciplineCaseAdmin(admin.ModelAdmin):
    list_display = ("case_number","student_name","student_admission_no","category","incident_date","status","urgent","assigned_officer")
    list_filter = ("status","urgent","category","incident_date")
    search_fields = ("case_number","student_name","student_admission_no","description")
    readonly_fields = ("case_number","created_at","updated_at","closed_at")
    inlines = [StatementInline, ActionInline, MeetingInline]

for model in [DisciplineCategory, DisciplinePolicy, DisciplineInvolvedParty, DisciplineIncidentReport,
              DisciplineStatement, DisciplineMeeting, DisciplineDecision, DisciplineAction,
              DisciplineImprovementPlan, DisciplineCommunication, DisciplineAppeal, DisciplineAuditLog]:
    try: admin.site.register(model)
    except admin.sites.AlreadyRegistered: pass
