from database_modules import (
    DatabaseCommonMixin,
    DatabaseFeedbackMixin,
    DatabaseJobsMixin,
    DatabaseMessagesMixin,
    DatabaseSessionsMixin,
    DatabaseVectorMixin,
)


class Database(
    DatabaseCommonMixin,
    DatabaseJobsMixin,
    DatabaseVectorMixin,
    DatabaseMessagesMixin,
    DatabaseSessionsMixin,
    DatabaseFeedbackMixin,
):
    """Composed Firestore data access layer split into focused mixins."""
