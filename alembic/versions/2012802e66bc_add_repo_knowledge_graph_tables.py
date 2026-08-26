"""add repo knowledge graph tables

Revision ID: 2012802e66bc
Revises: c4f8a1d9e2b6
Create Date: 2026-08-26 08:30:05.137314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2012802e66bc'
down_revision: Union[str, Sequence[str], None] = 'c4f8a1d9e2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'repo_graph_nodes',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('monitored_repo_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('file_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('language', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('summary', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('symbols', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('imports', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('loc', sa.Integer(), nullable=False),
        sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('embedding_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['monitored_repo_id'], ['monitored_repos.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_repo_graph_nodes_monitored_repo_id'), 'repo_graph_nodes', ['monitored_repo_id'], unique=False)
    op.create_index(op.f('ix_repo_graph_nodes_file_path'), 'repo_graph_nodes', ['file_path'], unique=False)
    op.create_index(op.f('ix_repo_graph_nodes_content_hash'), 'repo_graph_nodes', ['content_hash'], unique=False)

    op.create_table(
        'repo_graph_edges',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('monitored_repo_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('source_node_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('target_node_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('edge_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['monitored_repo_id'], ['monitored_repos.id'], ),
        sa.ForeignKeyConstraint(['source_node_id'], ['repo_graph_nodes.id'], ),
        sa.ForeignKeyConstraint(['target_node_id'], ['repo_graph_nodes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_repo_graph_edges_monitored_repo_id'), 'repo_graph_edges', ['monitored_repo_id'], unique=False)
    op.create_index(op.f('ix_repo_graph_edges_source_node_id'), 'repo_graph_edges', ['source_node_id'], unique=False)
    op.create_index(op.f('ix_repo_graph_edges_target_node_id'), 'repo_graph_edges', ['target_node_id'], unique=False)

    op.create_table(
        'repo_architecture_summaries',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('monitored_repo_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('overview', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('project_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('languages', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('module_breakdown_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('node_count', sa.Integer(), nullable=False),
        sa.Column('edge_count', sa.Integer(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('built_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['monitored_repo_id'], ['monitored_repos.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_repo_architecture_summaries_monitored_repo_id'), 'repo_architecture_summaries', ['monitored_repo_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_repo_architecture_summaries_monitored_repo_id'), table_name='repo_architecture_summaries')
    op.drop_table('repo_architecture_summaries')
    op.drop_index(op.f('ix_repo_graph_edges_target_node_id'), table_name='repo_graph_edges')
    op.drop_index(op.f('ix_repo_graph_edges_source_node_id'), table_name='repo_graph_edges')
    op.drop_index(op.f('ix_repo_graph_edges_monitored_repo_id'), table_name='repo_graph_edges')
    op.drop_table('repo_graph_edges')
    op.drop_index(op.f('ix_repo_graph_nodes_content_hash'), table_name='repo_graph_nodes')
    op.drop_index(op.f('ix_repo_graph_nodes_file_path'), table_name='repo_graph_nodes')
    op.drop_index(op.f('ix_repo_graph_nodes_monitored_repo_id'), table_name='repo_graph_nodes')
    op.drop_table('repo_graph_nodes')
