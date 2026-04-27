from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa


def test_initial_migration_creates_each_named_enum_exactly_once() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0001_initial_schema.py"
    )
    spec = spec_from_file_location("migration_0001_initial_schema", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.NAMED_ENUMS
    assert all(enum_type.create_type is False for enum_type in migration.NAMED_ENUMS)

    statements: list[str] = []
    holder: dict[str, sa.Engine] = {}

    def dump(sql, *multiparams, **params) -> None:  # type: ignore[no-untyped-def]
        compiled = str(sql.compile(dialect=holder["engine"].dialect))
        statements.append(" ".join(compiled.split()))

    holder["engine"] = sa.create_mock_engine("postgresql://", dump)

    for index, enum_type in enumerate(migration.NAMED_ENUMS):
        enum_type.create(holder["engine"], checkfirst=False)
        probe = sa.Table(
            f"enum_probe_{index}",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("value", enum_type, nullable=False),
        )
        probe.create(holder["engine"])

    create_type_statements = [statement for statement in statements if statement.startswith("CREATE TYPE")]

    assert len(create_type_statements) == len(migration.NAMED_ENUMS)
    for enum_type in migration.NAMED_ENUMS:
        assert (
            sum(f"CREATE TYPE {enum_type.name} AS ENUM" in statement for statement in create_type_statements)
            == 1
        )
