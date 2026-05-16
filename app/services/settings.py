from .. import db
from ..auth import SENTINEL_USER_ID
from ..schemas import AppSettings, AppSettingsPatch
from ._helpers import validated_cols


async def get_settings() -> AppSettings:
    """Return the singleton app_settings row. Inserts if missing."""
    row = await db.fetchrow(
        "SELECT * FROM app_settings WHERE user_id = %s LIMIT 1",
        SENTINEL_USER_ID,
    )
    if row is None:
        await db.execute(
            "INSERT INTO app_settings (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            SENTINEL_USER_ID,
        )
        return AppSettings()
    return AppSettings.model_validate(row)


async def update_settings(patch: AppSettingsPatch) -> AppSettings:
    """Apply the patch to the singleton row. Insert with the patch applied if missing.

    `exclude_none=True` matches the convention every other patch service
    uses (courses, slots, lectures, …) — without it, a caller that passes
    `timezone=None` would overwrite a valid timezone with NULL, which
    then fails AppSettings re-validation. Caught by the MCP-tool tests
    in Batch C2 — the `update_app_settings` MCP wrapper passes every
    parameter (None included) into AppSettingsPatch.
    """
    data = patch.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if not data:
        return await get_settings()

    # Build SET clause: "key1 = %s, key2 = %s, …". Column names come from
    # the Pydantic schema (not user input), so f-string interpolation is safe.
    cols = validated_cols(AppSettingsPatch, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    values = [data[c] for c in cols]

    row = await db.fetchrow(
        f"UPDATE app_settings SET {set_clause} WHERE user_id = %s RETURNING *",
        *values, SENTINEL_USER_ID,
    )
    if row is None:
        # Row missing — upsert (ON CONFLICT) rather than bare INSERT, so two
        # concurrent first-callers don't race the PK constraint into a 500.
        insert_cols = ["user_id", *cols]
        placeholders = ", ".join(["%s"] * len(insert_cols))
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
        row = await db.fetchrow(
            f"INSERT INTO app_settings ({', '.join(insert_cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (user_id) DO UPDATE SET {update_set} "
            f"RETURNING *",
            SENTINEL_USER_ID, *values,
        )
    return AppSettings.model_validate(row)
