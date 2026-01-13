---
title: "Implement database schema migrations with Alembic"
labels: ["enhancement", "database", "infrastructure"]
---

## Problem

Currently, the application uses SQLAlchemy's `Base.metadata.create_all()` for database initialization, which only creates tables if they don't exist. This approach has significant limitations:

1. **No schema evolution**: When models are updated, existing database schemas don't automatically migrate
2. **Manual migration required**: Schema changes require manual SQL scripts or dropping/recreating tables
3. **Production risk**: Schema drift between code and database can cause runtime errors
4. **Development friction**: Developers must manually sync their local databases after pulling model changes

### Recent Impact

A recent addition of `is_guest` and `added_by_user_id` columns to the `User` model caused production failures because existing databases didn't have these columns. A temporary migration script (`scripts/fix_db_schema.py`) was created as a workaround.

## Proposed Solution

Implement proper database migrations using **Alembic**, the de facto standard migration tool for SQLAlchemy.

### Benefits

- **Automatic schema versioning**: Track all database changes in version-controlled migration files
- **Safe schema evolution**: Apply incremental changes without data loss
- **Rollback capability**: Revert problematic migrations if needed
- **Environment consistency**: Ensure dev, staging, and production databases stay in sync
- **Audit trail**: Clear history of all schema changes

### Implementation Tasks

- [ ] Install Alembic dependency
- [ ] Initialize Alembic configuration (`alembic init`)
- [ ] Configure Alembic to use application's database URL
- [ ] Generate initial migration from current models
- [ ] Update deployment process to run migrations automatically
- [ ] Document migration workflow for developers
- [ ] Add migration validation to CI/CD pipeline

### Migration Workflow

**For developers:**
```bash
# After modifying models
alembic revision --autogenerate -m "Add new column"
alembic upgrade head
```

**For deployment:**
```bash
# Run before starting the application
alembic upgrade head
python -m src.bot.main
```

### References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Migrations Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

### Priority

**Medium-High** - While the application works with the temporary fix, proper migration tooling is essential for sustainable development and production stability.
