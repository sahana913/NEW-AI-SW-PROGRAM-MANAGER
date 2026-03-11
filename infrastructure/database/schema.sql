-- AI SW Program Manager - PostgreSQL Database Schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants table (for reference)
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tenants_name ON tenants(tenant_name);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    project_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL CHECK (source IN ('JIRA', 'AZURE_DEVOPS')),
    external_project_id VARCHAR(255),
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_projects_tenant ON projects(tenant_id);
CREATE INDEX idx_projects_source ON projects(source);
CREATE INDEX idx_projects_external_id ON projects(external_project_id);

-- Sprints table
CREATE TABLE IF NOT EXISTS sprints (
    sprint_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    sprint_name VARCHAR(255) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    velocity DECIMAL(10,2),
    completed_points DECIMAL(10,2),
    planned_points DECIMAL(10,2),
    completion_rate DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_sprints_project ON sprints(project_id);
CREATE INDEX idx_sprints_dates ON sprints(start_date, end_date);
CREATE INDEX idx_sprints_project_dates ON sprints(project_id, start_date DESC);

-- Backlog items table
CREATE TABLE IF NOT EXISTS backlog_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    external_item_id VARCHAR(255),
    item_type VARCHAR(50) CHECK (item_type IN ('bug', 'feature', 'technical_debt', 'other')),
    priority VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    age_days INTEGER,
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_backlog_project ON backlog_items(project_id);
CREATE INDEX idx_backlog_status ON backlog_items(status);
CREATE INDEX idx_backlog_type ON backlog_items(item_type);
CREATE INDEX idx_backlog_project_status ON backlog_items(project_id, status);

-- Milestones table
CREATE TABLE IF NOT EXISTS milestones (
    milestone_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    milestone_name VARCHAR(255) NOT NULL,
    due_date DATE NOT NULL,
    completion_percentage DECIMAL(5,2) DEFAULT 0,
    status VARCHAR(50) CHECK (status IN ('ON_TRACK', 'AT_RISK', 'DELAYED', 'COMPLETED')),
    source VARCHAR(50) CHECK (source IN ('JIRA', 'AZURE_DEVOPS', 'SOW_EXTRACTION', 'MANUAL')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_milestones_project ON milestones(project_id);
CREATE INDEX idx_milestones_due_date ON milestones(due_date);
CREATE INDEX idx_milestones_status ON milestones(status);
CREATE INDEX idx_milestones_project_status ON milestones(project_id, status);

-- Resources table
CREATE TABLE IF NOT EXISTS resources (
    resource_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    external_user_id VARCHAR(255),
    allocated_hours DECIMAL(10,2),
    capacity DECIMAL(10,2),
    utilization_rate DECIMAL(5,2),
    week_start_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_resources_project ON resources(project_id);
CREATE INDEX idx_resources_week ON resources(week_start_date);
CREATE INDEX idx_resources_project_week ON resources(project_id, week_start_date DESC);

-- Dependencies table
CREATE TABLE IF NOT EXISTS dependencies (
    dependency_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    source_task_id VARCHAR(255) NOT NULL,
    target_task_id VARCHAR(255) NOT NULL,
    dependency_type VARCHAR(50) CHECK (dependency_type IN ('BLOCKS', 'RELATES_TO')),
    status VARCHAR(50) CHECK (status IN ('ACTIVE', 'RESOLVED')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_dependencies_project ON dependencies(project_id);
CREATE INDEX idx_dependencies_source ON dependencies(source_task_id);
CREATE INDEX idx_dependencies_target ON dependencies(target_task_id);

-- Health scores table (for history tracking)
CREATE TABLE IF NOT EXISTS health_scores (
    health_score_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    health_score INTEGER NOT NULL CHECK (health_score >= 0 AND health_score <= 100),
    velocity_score INTEGER,
    backlog_score INTEGER,
    milestone_score INTEGER,
    risk_score INTEGER,
    rag_status VARCHAR(10) CHECK (rag_status IN ('GREEN', 'AMBER', 'RED')),
    calculated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_project FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    CONSTRAINT fk_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_health_scores_project ON health_scores(project_id);
CREATE INDEX idx_health_scores_calculated_at ON health_scores(calculated_at DESC);
CREATE INDEX idx_health_scores_project_time ON health_scores(project_id, calculated_at DESC);

-- Materialized view for dashboard metrics
CREATE MATERIALIZED VIEW IF NOT EXISTS project_metrics_summary AS
SELECT 
    p.project_id,
    p.tenant_id,
    p.project_name,
    p.source,
    COUNT(DISTINCT s.sprint_id) as total_sprints,
    AVG(s.velocity) as avg_velocity,
    AVG(s.completion_rate) as avg_completion_rate,
    COUNT(DISTINCT b.item_id) as total_backlog_items,
    COUNT(DISTINCT CASE WHEN b.status = 'OPEN' THEN b.item_id END) as open_backlog_items,
    COUNT(DISTINCT m.milestone_id) as total_milestones,
    COUNT(DISTINCT CASE WHEN m.status = 'COMPLETED' THEN m.milestone_id END) as completed_milestones,
    COUNT(DISTINCT CASE WHEN m.status = 'ON_TRACK' THEN m.milestone_id END) as on_track_milestones,
    COUNT(DISTINCT CASE WHEN m.status = 'AT_RISK' THEN m.milestone_id END) as at_risk_milestones,
    COUNT(DISTINCT CASE WHEN m.status = 'DELAYED' THEN m.milestone_id END) as delayed_milestones,
    AVG(r.utilization_rate) as avg_utilization,
    MAX(p.last_sync_at) as last_sync_at
FROM projects p
LEFT JOIN sprints s ON p.project_id = s.project_id
LEFT JOIN backlog_items b ON p.project_id = b.project_id
LEFT JOIN milestones m ON p.project_id = m.project_id
LEFT JOIN resources r ON p.project_id = r.project_id
GROUP BY p.project_id, p.tenant_id, p.project_name, p.source;

CREATE UNIQUE INDEX idx_project_metrics_summary ON project_metrics_summary(project_id);
CREATE INDEX idx_project_metrics_tenant ON project_metrics_summary(tenant_id);

-- Function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_project_metrics_summary()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY project_metrics_summary;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update trigger to all tables
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sprints_updated_at BEFORE UPDATE ON sprints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_backlog_items_updated_at BEFORE UPDATE ON backlog_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_milestones_updated_at BEFORE UPDATE ON milestones
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_resources_updated_at BEFORE UPDATE ON resources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dependencies_updated_at BEFORE UPDATE ON dependencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust as needed for your Lambda execution role)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lambda_execution_role;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lambda_execution_role;
