# Django Disciplinary Management Module

Standalone first implementation intended to be integrated with an existing school ERP later.

## Included
- Admin dashboard, case register, incident reports, case status workflow
- Staff incident submission and case access for reporters/assignees
- Student/parent response capture scaffold
- Categories and policy records
- Statements, meetings, decisions, actions, improvement plans and appeals
- Communications records, reports and audit log
- Django admin registrations and responsive templates

## Important integration note
To keep this app installable before the ERP is linked, the case model temporarily stores student and parent display/contact fields as text. During integration, replace these with foreign keys to the ERP's existing Student, Parent/Guardian and Staff models. Do not duplicate user accounts. The parent/student portal routes are scaffolding until the ERP can securely map logged-in accounts to a student or guardian. Do not expose those portals to real users until that mapping and object-level access control have been implemented.

## Install
1. Copy the `discipline` folder into the same directory as your other Django apps.
2. Add `discipline.apps.DisciplineConfig` to `INSTALLED_APPS`.
3. In the project's main `urls.py`, add:
   `path("discipline/", include("discipline.urls"))`
4. Run:
   `python manage.py makemigrations discipline`
   `python manage.py migrate`
   `python manage.py check`
5. Sign in using an account with `is_staff=True`, a superuser account, or membership in one of these Django groups: `Discipline Admin`, `Principal`, `Disciplinary Officer`.
6. Visit `/discipline/`.

## File uploads
Configure `MEDIA_ROOT` and `MEDIA_URL`, and configure private media serving in production. Disciplinary evidence is sensitive and must not be served as public static files.

## Production checklist before linking/live use
- Map student, parent/guardian and staff identities to existing ERP models.
- Implement object-level permission checks for student and parent records.
- Add school-specific safeguarding/escalation policy and approved decision workflow.
- Configure email/SMS provider and notification delivery.
- Review file upload restrictions, retention, audit access, privacy and backups.
- Add automated tests for unauthorized access, case lifecycle, forms and file uploads.
- Review applicable Kenyan data-protection, child-protection and education requirements.

## Design
Responsive interface uses a neutral layout with a deep maroon accent. Templates can be adapted to the existing ERP base template during integration.


## ERP integration upgrade package

This package adds a nullable foreign key from `DisciplineCase` to the existing
`students.Student` model. Existing cases remain intact; the new field can be
left empty for legacy records. When a student is selected on a new or edited
case, the display name, admission number, class/stream, and parent contact
snapshot are refreshed from that student record.

Parent accounts can see only cases for children linked to their existing
`parents.Parent.children` relationship, in addition to the normal reporter,
assigned-officer, and manager access. Student-account portal mapping is not
enabled because the inspected Student model has no user-account relationship.
Case status changes now require POST and CSRF protection.

After copying the updated app, run `python manage.py migrate` and
`python manage.py check`. Do not expose evidence files through public media
URLs in production; configure authenticated private-file delivery before
showing attachment links to users.
