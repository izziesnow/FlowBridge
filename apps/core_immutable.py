"""Shared support for append-only (immutable) records.

Immutability is enforced twice:

1. In the application: ``ImmutableModel.save`` refuses to update an existing
   row and ``delete`` always refuses. Bulk ``QuerySet.update``/``delete``
   calls bypass these methods, which is why the second layer exists.
2. In PostgreSQL: a ``BEFORE UPDATE OR DELETE`` row trigger raises an error.
   ``immutable_trigger_sql`` returns the SQL used in each app's migration.

Neither layer protects against a database superuser who drops the trigger;
that boundary is stated in Section 1.4 of the write-up.
"""
from django.db import models


class ImmutableRecordError(Exception):
    """Raised when code tries to change or delete an immutable record."""


class ImmutableModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} records cannot be changed once saved.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError(f"{type(self).__name__} records cannot be deleted.")


FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION flowbridge_refuse_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Flowbridge: % records are immutable (% refused)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""


def immutable_trigger_sql(table):
    forward = FUNCTION_SQL + f"""
DROP TRIGGER IF EXISTS {table}_immutable ON {table};
CREATE TRIGGER {table}_immutable
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION flowbridge_refuse_change();
"""
    reverse = f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};"
    return forward, reverse
