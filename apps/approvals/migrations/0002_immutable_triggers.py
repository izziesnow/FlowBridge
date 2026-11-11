"""PostgreSQL triggers that refuse UPDATE and DELETE on evidence tables.

This is the database half of evidence immutability (NFR04). The model half is
``apps.core_immutable.ImmutableModel``. Bulk queryset updates and raw SQL
bypass model methods but not these triggers.
"""
from django.db import migrations

from apps.core_immutable import immutable_trigger_sql

TABLES = [
    "approvals_revision",
    "approvals_revisiondocument",
    "approvals_documentversion",
    "approvals_decision",
]


class Migration(migrations.Migration):
    dependencies = [("approvals", "0001_initial")]

    operations = [
        migrations.RunSQL(*immutable_trigger_sql(table)) for table in TABLES
    ]
