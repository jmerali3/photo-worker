#!/usr/bin/env python3

import asyncio
import logging
import signal
import sys
from typing import Optional

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker._workflow_instance import UnsandboxedWorkflowRunner

from worker.config import load_config
from worker.utils.db import get_shared_db_helper, close_shared_pool
from worker.workflows.image_processing import ImageProcessingWorkflow
from worker.activities.io_s3 import verify_and_locate_asset
from worker.activities.ocr_textract import ocr_textract
from worker.activities.persist import persist_artifacts
from worker.activities.tagging_llm import tag_from_ocr

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class WorkerRunner:
    """
    Temporal worker runner that manages the worker lifecycle.
    """

    def __init__(self):
        self.config = load_config()
        self.client: Optional[Client] = None
        self.worker: Optional[Worker] = None
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Initialize the Temporal client."""
        try:
            self.client = await Client.connect(
                self.config.temporal.target,
                namespace=self.config.temporal.namespace
            )
            logger.info(
                f"Connected to Temporal at {self.config.temporal.target} "
                f"(namespace: {self.config.temporal.namespace})"
            )

            # Initialize shared DB pool early so activities can reuse it
            try:
                get_shared_db_helper(self.config.database)
                logger.info("Shared database pool initialized")
            except Exception as db_init_err:
                logger.error(f"Failed to initialize shared DB pool: {db_init_err}")
                raise
        except Exception as e:
            logger.error(f"Failed to connect to Temporal: {e}")
            raise

    async def create_worker(self) -> Worker:
        """Create and configure the Temporal worker."""
        if not self.client:
            raise RuntimeError("Client not initialized")

        # Register workflows and activities
        workflows = [ImageProcessingWorkflow]
        activities = [
            verify_and_locate_asset,
            ocr_textract,
            persist_artifacts,
            tag_from_ocr  # Future tagging activity
        ]

        # Create worker with configuration
        worker = Worker(
            self.client,
            task_queue=self.config.temporal.task_queue,
            workflows=workflows,
            activities=activities,
            workflow_runner=UnsandboxedWorkflowRunner(),
            max_concurrent_activities=self.config.temporal.max_concurrent_activities,
            max_concurrent_workflow_tasks=self.config.temporal.max_concurrent_workflow_tasks
        )

        logger.info(
            f"Worker created for task queue '{self.config.temporal.task_queue}' "
            f"(max activities: {self.config.temporal.max_concurrent_activities}, "
            f"max workflow tasks: {self.config.temporal.max_concurrent_workflow_tasks})"
        )

        return worker

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def run(self):
        """Run the worker with graceful shutdown support."""
        try:
            # Initialize client
            await self.initialize()

            # Create worker
            self.worker = await self.create_worker()

            # Setup signal handlers
            self.setup_signal_handlers()

            # Start worker
            logger.info("Starting Temporal worker...")
            worker_task = asyncio.create_task(self.worker.run())

            # Wait for shutdown signal or worker completion
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())
            done, pending = await asyncio.wait(
                [worker_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if shutdown_task in done:
                logger.info("Shutdown signal received, stopping worker...")
                await self.worker.shutdown()

            logger.info("Worker stopped successfully")

        except Exception as e:
            logger.error(f"Worker error: {e}")
            sys.exit(1)

        finally:
            # Close client connection
            if self.client:
                close_attr = getattr(self.client, "close", None)
                if callable(close_attr):
                    try:
                        await close_attr()  # type: ignore[misc]
                    except TypeError:
                        # Temporal client does not expose an async close method in 1.7.0
                        pass
                    else:
                        logger.info("Temporal client connection closed")

            # Close shared DB pool
            try:
                close_shared_pool()
            except Exception as e:
                logger.warning(f"Error closing shared DB pool: {e}")


async def main():
    """Main entry point."""
    logger.info("Starting photo-worker Temporal worker")

    # Set log level from config
    config = load_config()
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # Log configuration
    logger.info(f"Configuration:")
    logger.info(f"  Temporal target: {config.temporal.target}")
    logger.info(f"  Temporal namespace: {config.temporal.namespace}")
    logger.info(f"  Task queue: {config.temporal.task_queue}")
    logger.info(f"  S3 bucket: {config.s3.bucket}")
    logger.info(f"  S3 region: {config.s3.region}")
    logger.info(f"  Database: {config.database.host}:{config.database.port}/{config.database.database}")

    # Create and run worker
    runner = WorkerRunner()
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed to start: {e}")
        sys.exit(1)
