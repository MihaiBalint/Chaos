"""create table line_section

Revision ID: 5a14937a07a
Revises: 26f7840832a6
Create Date: 2014-09-02 10:36:26.128864

"""

# revision identifiers, used by Alembic.
revision = '5a14937a07a'
down_revision = '26f7840832a6'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('line_section',
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('id', postgresql.UUID(), nullable=False),
    sa.Column('line_object_id', postgresql.UUID(), nullable=False),
    sa.Column('start_object_id', postgresql.UUID(), nullable=False),
    sa.Column('end_object_id', postgresql.UUID(), nullable=False),
    sa.Column('sens', sa.Integer(), nullable=True),
    sa.Column('object_id', postgresql.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['line_object_id'], [u'pt_object.id'], ),
    sa.ForeignKeyConstraint(['object_id'], [u'pt_object.id'], ),
    sa.ForeignKeyConstraint(['start_object_id'], [u'pt_object.id'], ),
    sa.ForeignKeyConstraint(['end_object_id'], [u'pt_object.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.execute("COMMIT")  # See https://bitbucket.org/zzzeek/alembic/issue/123
    op.execute("ALTER TYPE pt_object_type ADD VALUE 'line_section'")
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.execute("ALTER TABLE pt_object ALTER COLUMN type TYPE text")
    op.execute("DROP TYPE pt_object_type")
    op.execute("CREATE TYPE pt_object_type AS ENUM ('network', 'stop_area', 'line')")
    op.execute("UPDATE pt_object SET type=NULL where type='line_section'")
    op.execute("ALTER TABLE pt_object ALTER COLUMN type TYPE pt_object_type USING type::pt_object_type")
    op.drop_table("line_section")
    op.execute("DELETE FROM associate_impact_pt_object WHERE pt_object_id IN (SELECT id FROM pt_object WHERE type IS NULL)")
    op.execute("DELETE FROM pt_object WHERE type IS NULL")

    ### end Alembic commands ###
