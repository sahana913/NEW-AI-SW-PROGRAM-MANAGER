"""
Training Data Preparation Module

Extracts historical project data from RDS and prepares it for ML model training.
"""

import logging
from decimal import Decimal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TrainingDataPreparation:
    """Prepares training data for delay prediction models"""

    def __init__(self, db_connection):
        """
        Initialize training data preparation

        Args:
            db_connection: Database connection object
        """
        self.db_connection = db_connection

    def extract_historical_project_data(self, tenant_id: str = None) -> pd.DataFrame:
        """
        Extract historical project data from RDS

        Args:
            tenant_id: Optional tenant ID to filter data

        Returns:
            DataFrame with historical project data
        """
        logger.info(f"Extracting historical project data for tenant: {tenant_id}")

        query = """
            SELECT
                p.project_id,
                p.tenant_id,
                p.project_name,
                p.source,
                p.created_at as project_start_date,
                p.last_sync_at
            FROM projects p
            WHERE 1=1
        """

        params = []
        if tenant_id:
            query += " AND p.tenant_id = %s"
            params.append(tenant_id)

        query += " ORDER BY p.created_at"

        cursor = self.db_connection.cursor()
        cursor.execute(query, params)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)
        logger.info(f"Extracted {len(df)} projects")

        return df

    def extract_sprint_metrics(self, project_ids: List[str]) -> pd.DataFrame:
        """
        Extract sprint metrics for given projects

        Args:
            project_ids: List of project IDs

        Returns:
            DataFrame with sprint metrics
        """
        if not project_ids:
            return pd.DataFrame()

        logger.info(f"Extracting sprint metrics for {len(project_ids)} projects")

        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                s.project_id,
                s.sprint_id,
                s.sprint_name,
                s.start_date,
                s.end_date,
                s.velocity,
                s.completed_points,
                s.planned_points,
                s.completion_rate
            FROM sprints s
            WHERE s.project_id IN ({placeholders})
            ORDER BY s.project_id, s.start_date
        """

        cursor = self.db_connection.cursor()
        cursor.execute(query, project_ids)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        # Convert Decimal to float
        for col in [
            "velocity",
            "completed_points",
            "planned_points",
            "completion_rate",
        ]:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: float(x) if isinstance(x, Decimal) else x
                )

        logger.info(f"Extracted {len(df)} sprint records")

        return df

    def extract_backlog_metrics(self, project_ids: List[str]) -> pd.DataFrame:
        """
        Extract backlog metrics for given projects

        Args:
            project_ids: List of project IDs

        Returns:
            DataFrame with backlog metrics
        """
        if not project_ids:
            return pd.DataFrame()

        logger.info(f"Extracting backlog metrics for {len(project_ids)} projects")

        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                b.project_id,
                COUNT(*) as total_items,
                COUNT(CASE WHEN b.status = 'OPEN' THEN 1 END) as open_items,
                COUNT(CASE WHEN b.item_type = 'bug' THEN 1 END) as bug_count,
                COUNT(CASE WHEN b.item_type = 'feature' THEN 1 END) as feature_count,
                COUNT(CASE WHEN b.item_type = 'technical_debt' THEN 1 END) as tech_debt_count,
                AVG(b.age_days) as avg_age_days
            FROM backlog_items b
            WHERE b.project_id IN ({placeholders})
            GROUP BY b.project_id
        """

        cursor = self.db_connection.cursor()
        cursor.execute(query, project_ids)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        # Convert Decimal to float
        if "avg_age_days" in df.columns:
            df["avg_age_days"] = df["avg_age_days"].apply(
                lambda x: float(x) if isinstance(x, Decimal) else x
            )

        logger.info(f"Extracted backlog metrics for {len(df)} projects")

        return df

    def extract_milestone_metrics(self, project_ids: List[str]) -> pd.DataFrame:
        """
        Extract milestone metrics for given projects

        Args:
            project_ids: List of project IDs

        Returns:
            DataFrame with milestone metrics
        """
        if not project_ids:
            return pd.DataFrame()

        logger.info(f"Extracting milestone metrics for {len(project_ids)} projects")

        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                m.project_id,
                COUNT(*) as total_milestones,
                COUNT(CASE WHEN m.status = 'COMPLETED' THEN 1 END) as completed_milestones,
                COUNT(CASE WHEN m.status = 'ON_TRACK' THEN 1 END) as on_track_milestones,
                COUNT(CASE WHEN m.status = 'AT_RISK' THEN 1 END) as at_risk_milestones,
                COUNT(CASE WHEN m.status = 'DELAYED' THEN 1 END) as delayed_milestones,
                AVG(m.completion_percentage) as avg_completion_percentage
            FROM milestones m
            WHERE m.project_id IN ({placeholders})
            GROUP BY m.project_id
        """

        cursor = self.db_connection.cursor()
        cursor.execute(query, project_ids)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        # Convert Decimal to float
        if "avg_completion_percentage" in df.columns:
            df["avg_completion_percentage"] = df["avg_completion_percentage"].apply(
                lambda x: float(x) if isinstance(x, Decimal) else x
            )

        logger.info(f"Extracted milestone metrics for {len(df)} projects")

        return df

    def extract_dependency_metrics(self, project_ids: List[str]) -> pd.DataFrame:
        """
        Extract dependency metrics for given projects

        Args:
            project_ids: List of project IDs

        Returns:
            DataFrame with dependency metrics
        """
        if not project_ids:
            return pd.DataFrame()

        logger.info(f"Extracting dependency metrics for {len(project_ids)} projects")

        placeholders = ",".join(["%s"] * len(project_ids))
        query = f"""
            SELECT
                d.project_id,
                COUNT(*) as total_dependencies,
                COUNT(CASE WHEN d.status = 'ACTIVE' THEN 1 END) as active_dependencies,
                COUNT(CASE WHEN d.dependency_type = 'BLOCKS' THEN 1 END) as blocking_dependencies
            FROM dependencies d
            WHERE d.project_id IN ({placeholders})
            GROUP BY d.project_id
        """

        cursor = self.db_connection.cursor()
        cursor.execute(query, project_ids)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        logger.info(f"Extracted dependency metrics for {len(df)} projects")

        return df

    def engineer_features(
        self,
        projects_df: pd.DataFrame,
        sprints_df: pd.DataFrame,
        backlog_df: pd.DataFrame,
        milestones_df: pd.DataFrame,
        dependencies_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Engineer features from raw data

        Args:
            projects_df: Projects DataFrame
            sprints_df: Sprints DataFrame
            backlog_df: Backlog DataFrame
            milestones_df: Milestones DataFrame
            dependencies_df: Dependencies DataFrame

        Returns:
            DataFrame with engineered features
        """
        logger.info("Engineering features from raw data")

        features_list = []

        for _, project in projects_df.iterrows():
            project_id = str(project["project_id"])

            # Sprint-based features
            project_sprints = sprints_df[sprints_df["project_id"] == project_id]

            if len(project_sprints) >= 4:
                # Velocity trend (last 4 sprints)
                recent_sprints = project_sprints.tail(4)
                velocities = recent_sprints["velocity"].values
                velocity_trend = (
                    np.polyfit(range(len(velocities)), velocities, 1)[0]
                    if len(velocities) > 1
                    else 0
                )
                avg_velocity = np.mean(velocities)
                velocity_std = np.std(velocities)

                # Completion rate
                avg_completion_rate = recent_sprints["completion_rate"].mean()
            else:
                velocity_trend = 0
                avg_velocity = 0
                velocity_std = 0
                avg_completion_rate = 0

            # Backlog features
            project_backlog = backlog_df[backlog_df["project_id"] == project_id]
            if not project_backlog.empty:
                total_backlog = project_backlog["total_items"].values[0]
                open_backlog = project_backlog["open_items"].values[0]
                backlog_ratio = open_backlog / total_backlog if total_backlog > 0 else 0
                avg_age = (
                    project_backlog["avg_age_days"].values[0]
                    if project_backlog["avg_age_days"].values[0]
                    else 0
                )
            else:
                total_backlog = 0
                open_backlog = 0
                backlog_ratio = 0
                avg_age = 0

            # Milestone features
            project_milestones = milestones_df[
                milestones_df["project_id"] == project_id
            ]
            if not project_milestones.empty:
                total_milestones = project_milestones["total_milestones"].values[0]
                completed_milestones = project_milestones[
                    "completed_milestones"
                ].values[0]
                at_risk_milestones = project_milestones["at_risk_milestones"].values[0]
                delayed_milestones = project_milestones["delayed_milestones"].values[0]
                milestone_completion_rate = (
                    completed_milestones / total_milestones
                    if total_milestones > 0
                    else 0
                )
                avg_milestone_completion = project_milestones[
                    "avg_completion_percentage"
                ].values[0]
            else:
                total_milestones = 0
                completed_milestones = 0
                at_risk_milestones = 0
                delayed_milestones = 0
                milestone_completion_rate = 0
                avg_milestone_completion = 0

            # Dependency features
            project_dependencies = dependencies_df[
                dependencies_df["project_id"] == project_id
            ]
            if not project_dependencies.empty:
                total_dependencies = project_dependencies["total_dependencies"].values[
                    0
                ]
                active_dependencies = project_dependencies[
                    "active_dependencies"
                ].values[0]
                blocking_dependencies = project_dependencies[
                    "blocking_dependencies"
                ].values[0]
            else:
                total_dependencies = 0
                active_dependencies = 0
                blocking_dependencies = 0

            features = {
                "project_id": project_id,
                "tenant_id": str(project["tenant_id"]),
                "velocity_trend": velocity_trend,
                "avg_velocity": avg_velocity,
                "velocity_std": velocity_std,
                "avg_completion_rate": avg_completion_rate,
                "total_backlog": total_backlog,
                "open_backlog": open_backlog,
                "backlog_ratio": backlog_ratio,
                "avg_backlog_age": avg_age,
                "total_milestones": total_milestones,
                "completed_milestones": completed_milestones,
                "at_risk_milestones": at_risk_milestones,
                "delayed_milestones": delayed_milestones,
                "milestone_completion_rate": milestone_completion_rate,
                "avg_milestone_completion": avg_milestone_completion,
                "total_dependencies": total_dependencies,
                "active_dependencies": active_dependencies,
                "blocking_dependencies": blocking_dependencies,
            }

            features_list.append(features)

        features_df = pd.DataFrame(features_list)
        logger.info(f"Engineered features for {len(features_df)} projects")

        return features_df

    def label_delay_outcomes(
        self, features_df: pd.DataFrame, milestones_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Label data with actual delay outcomes

        Args:
            features_df: Features DataFrame
            milestones_df: Milestones DataFrame with actual outcomes

        Returns:
            DataFrame with delay labels
        """
        logger.info("Labeling data with delay outcomes")

        # For each project, determine if it was delayed
        # A project is considered delayed if it has any delayed milestones
        labeled_data = features_df.copy()

        delay_labels = []
        delay_days = []

        for _, row in labeled_data.iterrows():
            project_id = row["project_id"]

            # Check if project has delayed milestones
            is_delayed = row["delayed_milestones"] > 0

            # Estimate delay days based on milestone metrics
            # This is a simplified approach - in production, you'd track actual vs planned dates
            if is_delayed:
                # Rough estimate: delayed milestones * average delay per milestone
                estimated_delay = (
                    row["delayed_milestones"] * 14
                )  # Assume 2 weeks per delayed milestone
            else:
                estimated_delay = 0

            delay_labels.append(1 if is_delayed else 0)
            delay_days.append(estimated_delay)

        labeled_data["is_delayed"] = delay_labels
        labeled_data["delay_days"] = delay_days

        logger.info(
            f"Labeled {len(labeled_data)} projects: {sum(delay_labels)} delayed, {len(delay_labels) - sum(delay_labels)} on-time"
        )

        return labeled_data

    def split_train_val_test(
        self,
        labeled_data: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into training, validation, and test sets

        Args:
            labeled_data: Labeled DataFrame
            train_ratio: Training set ratio
            val_ratio: Validation set ratio
            test_ratio: Test set ratio

        Returns:
            Tuple of (train_df, val_df, test_df)
        """
        logger.info(
            f"Splitting data: train={train_ratio}, val={val_ratio}, test={test_ratio}"
        )

        # Shuffle data
        shuffled_data = labeled_data.sample(frac=1, random_state=42).reset_index(
            drop=True
        )

        n = len(shuffled_data)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)

        train_df = shuffled_data[:train_end]
        val_df = shuffled_data[train_end:val_end]
        test_df = shuffled_data[val_end:]

        logger.info(
            f"Split complete: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
        )

        return train_df, val_df, test_df

    def prepare_training_data(self, tenant_id: str = None) -> Dict[str, pd.DataFrame]:
        """
        Complete pipeline to prepare training data

        Args:
            tenant_id: Optional tenant ID to filter data

        Returns:
            Dictionary with train, val, and test DataFrames
        """
        logger.info("Starting training data preparation pipeline")

        # Extract data
        projects_df = self.extract_historical_project_data(tenant_id)

        if projects_df.empty:
            logger.warning("No projects found")
            return {
                "train": pd.DataFrame(),
                "val": pd.DataFrame(),
                "test": pd.DataFrame(),
            }

        project_ids = [str(pid) for pid in projects_df["project_id"].tolist()]

        sprints_df = self.extract_sprint_metrics(project_ids)
        backlog_df = self.extract_backlog_metrics(project_ids)
        milestones_df = self.extract_milestone_metrics(project_ids)
        dependencies_df = self.extract_dependency_metrics(project_ids)

        # Engineer features
        features_df = self.engineer_features(
            projects_df, sprints_df, backlog_df, milestones_df, dependencies_df
        )

        # Label data
        labeled_data = self.label_delay_outcomes(features_df, milestones_df)

        # Split data
        train_df, val_df, test_df = self.split_train_val_test(labeled_data)

        logger.info("Training data preparation complete")

        return {"train": train_df, "val": val_df, "test": test_df}
