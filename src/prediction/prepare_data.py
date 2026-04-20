"""
Script to prepare training data for delay prediction model
"""

from src.shared.database import get_db_connection
from src.prediction.training_data_preparation import TrainingDataPreparation
import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main function to prepare training data"""
    parser = argparse.ArgumentParser(
        description="Prepare training data for delay prediction model"
    )
    parser.add_argument(
        "--tenant-id", type=str, help="Optional tenant ID to filter data"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./training_data",
        help="Output directory for training data",
    )

    args = parser.parse_args()

    logger.info("Starting training data preparation")
    logger.info(f"Tenant ID: {args.tenant_id}")
    logger.info(f"Output directory: {args.output_dir}")

    # Create output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Get database connection
    try:
        db_conn = get_db_connection()
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return 1

    try:
        # Prepare training data
        prep = TrainingDataPreparation(db_conn)
        data_splits = prep.prepare_training_data(tenant_id=args.tenant_id)

        # Save data splits
        for split_name, df in data_splits.items():
            if not df.empty:
                output_file = output_path / f"{split_name}.csv"
                df.to_csv(output_file, index=False)
                logger.info(
                    f"Saved {split_name} data to {output_file} ({len(df)} records)"
                )
            else:
                logger.warning(f"No data for {split_name} split")

        # Save metadata
        metadata = {
            "tenant_id": args.tenant_id,
            "train_records": len(data_splits["train"]),
            "val_records": len(data_splits["val"]),
            "test_records": len(data_splits["test"]),
            "features": (
                list(data_splits["train"].columns)
                if not data_splits["train"].empty
                else []
            ),
        }

        metadata_file = output_path / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved metadata to {metadata_file}")
        logger.info("Training data preparation complete")

        return 0

    except Exception as e:
        logger.error(f"Error preparing training data: {e}", exc_info=True)
        return 1

    finally:
        if db_conn:
            db_conn.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    sys.exit(main())
