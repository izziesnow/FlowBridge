"""Make reassignment records immutable at database level, like other evidence (NFR03, NFR04)."""
from django.db import migrations

from apps.core_immutable import immutable_trigger_sql


class Migration(migrations.Migration):
    dependencies = [("approvals", "0003_reminders_and_reassignment")]

    operations = [migrations.RunSQL(*immutable_trigger_sql("approvals_reassignment"))]
