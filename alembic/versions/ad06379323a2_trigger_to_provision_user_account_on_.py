"""trigger to provision user_account on auth signup

Revision ID: ad06379323a2
Revises: 5f264e877f31
Create Date: 2026-08-10 14:52:20.072432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad06379323a2'
down_revision: Union[str, Sequence[str], None] = '5f264e877f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
            INSERT INTO public.user_account (id, email, auth_provider_uid, created_at)
            VALUES (NEW.id, NEW.email, NEW.id::text, now())
            ON CONFLICT (auth_provider_uid) DO NOTHING;
            RETURN NEW;
        END;
        $$;
    """)

    op.execute("""
        CREATE TRIGGER on_auth_user_created
        AFTER INSERT ON auth.users
        FOR EACH ROW
        EXECUTE FUNCTION public.handle_new_user();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user();")

    