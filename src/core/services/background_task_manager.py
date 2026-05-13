"""
Background Task Manager for coordinating periodic and continuous tasks.

This service manages all background tasks across the application, preventing
conflicts and providing centralized control over task lifecycle.
"""

import asyncio
import logging
from typing import Dict, Callable, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger("background_task_manager")


class BackgroundTaskManager:
    """
    Coordinates all background tasks across modules.

    Features:
    - Periodic tasks with configurable intervals
    - Continuous tasks that run until stopped
    - Per-task locking to prevent concurrent execution
    - Graceful shutdown with cleanup
    - Task monitoring and status tracking
    """

    def __init__(self):
        """Initialize the background task manager."""
        self._tasks: Dict[str, asyncio.Task] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._task_info: Dict[str, Dict[str, Any]] = {}
        self._shutdown = False
        logger.info("BackgroundTaskManager initialized")

    async def register_periodic_task(
        self,
        name: str,
        coro: Callable,
        interval_hours: int,
        *,
        run_immediately: bool = False,
        error_handler: Optional[Callable] = None
    ) -> asyncio.Task:
        """
        Register a task that runs periodically at fixed intervals.

        Args:
            name: Unique identifier for the task
            coro: Coroutine function to execute
            interval_hours: Hours between executions
            run_immediately: If True, run once before starting interval
            error_handler: Optional error handler callback

        Returns:
            The created asyncio.Task

        Example:
            >>> await manager.register_periodic_task(
            ...     "uma_scraper",
            ...     uma_module.refresh_events,
            ...     interval_hours=6
            ... )
        """
        if name in self._tasks:
            logger.warning(f"Task '{name}' already registered, replacing")
            await self.stop_task(name)

        # Create lock for this task
        lock = asyncio.Lock()
        self._locks[name] = lock

        # Store task metadata
        self._task_info[name] = {
            "type": "periodic",
            "interval_hours": interval_hours,
            "last_run": None,
            "next_run": None,
            "error_count": 0,
        }

        async def periodic_wrapper():
            """Wrapper that handles periodic execution with locking."""
            interval_seconds = interval_hours * 3600

            # Run immediately if requested
            if run_immediately:
                await self._execute_with_lock(name, coro, error_handler)

            while not self._shutdown:
                try:
                    # Calculate next run time
                    next_run = datetime.now() + timedelta(hours=interval_hours)
                    self._task_info[name]["next_run"] = next_run

                    # Wait for interval
                    await asyncio.sleep(interval_seconds)

                    if self._shutdown:
                        break

                    # Execute the task
                    await self._execute_with_lock(name, coro, error_handler)

                except asyncio.CancelledError:
                    logger.info(f"Periodic task '{name}' cancelled")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in periodic task '{name}': {e}")
                    self._task_info[name]["error_count"] += 1
                    if error_handler:
                        try:
                            await error_handler(e)
                        except Exception as handler_error:
                            logger.error(f"Error handler failed for '{name}': {handler_error}")
                    # Wait a bit before retrying
                    await asyncio.sleep(60)

        # Create and store the task
        task = asyncio.create_task(periodic_wrapper())
        self._tasks[name] = task

        logger.info(f"Registered periodic task '{name}' (interval: {interval_hours}h)")
        return task

    async def register_continuous_task(
        self,
        name: str,
        coro: Callable,
        *,
        error_handler: Optional[Callable] = None
    ) -> asyncio.Task:
        """
        Register a task that runs continuously until stopped.

        Args:
            name: Unique identifier for the task
            coro: Coroutine function to execute continuously
            error_handler: Optional error handler callback

        Returns:
            The created asyncio.Task

        Example:
            >>> await manager.register_continuous_task(
            ...     "twitter_listener",
            ...     twitter_handler.listen
            ... )
        """
        if name in self._tasks:
            logger.warning(f"Task '{name}' already registered, replacing")
            await self.stop_task(name)

        # Create lock for this task
        lock = asyncio.Lock()
        self._locks[name] = lock

        # Store task metadata
        self._task_info[name] = {
            "type": "continuous",
            "start_time": datetime.now(),
            "error_count": 0,
        }

        async def continuous_wrapper():
            """Wrapper that handles continuous execution with error handling."""
            try:
                async with lock:
                    logger.info(f"Starting continuous task '{name}'")
                    await coro()
            except asyncio.CancelledError:
                logger.info(f"Continuous task '{name}' cancelled")
                raise
            except Exception as e:
                logger.error(f"Error in continuous task '{name}': {e}")
                self._task_info[name]["error_count"] += 1
                if error_handler:
                    try:
                        await error_handler(e)
                    except Exception as handler_error:
                        logger.error(f"Error handler failed for '{name}': {handler_error}")

        # Create and store the task
        task = asyncio.create_task(continuous_wrapper())
        self._tasks[name] = task

        logger.info(f"Registered continuous task '{name}'")
        return task

    async def _execute_with_lock(
        self,
        name: str,
        coro: Callable,
        error_handler: Optional[Callable]
    ):
        """Execute a task with locking and error handling."""
        lock = self._locks.get(name)
        if not lock:
            logger.error(f"No lock found for task '{name}'")
            return

        async with lock:
            try:
                logger.debug(f"Executing task '{name}'")
                start_time = datetime.now()

                await coro()

                # Update metadata
                self._task_info[name]["last_run"] = start_time
                execution_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"Task '{name}' completed in {execution_time:.2f}s")

            except Exception as e:
                logger.error(f"Error executing task '{name}': {e}", exc_info=True)
                self._task_info[name]["error_count"] += 1

                if error_handler:
                    try:
                        await error_handler(e)
                    except Exception as handler_error:
                        logger.error(f"Error handler failed for '{name}': {handler_error}")

    async def stop_task(self, name: str) -> bool:
        """
        Stop a specific task.

        Args:
            name: Name of the task to stop

        Returns:
            True if task was stopped, False if not found
        """
        task = self._tasks.get(name)
        if not task:
            logger.warning(f"Task '{name}' not found")
            return False

        logger.info(f"Stopping task '{name}'")
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Cleanup
        del self._tasks[name]
        if name in self._locks:
            del self._locks[name]
        if name in self._task_info:
            del self._task_info[name]

        logger.info(f"Task '{name}' stopped")
        return True

    async def stop_all(self):
        """Stop all running tasks gracefully."""
        logger.info(f"Stopping all {len(self._tasks)} tasks")
        self._shutdown = True

        # Cancel all tasks
        for name, task in list(self._tasks.items()):
            logger.info(f"Cancelling task '{name}'")
            task.cancel()

        # Wait for all tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        # Cleanup
        self._tasks.clear()
        self._locks.clear()
        self._task_info.clear()

        logger.info("All tasks stopped")

    def get_task_status(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific task.

        Args:
            name: Name of the task

        Returns:
            Dictionary with task status information, or None if not found
        """
        if name not in self._tasks:
            return None

        task = self._tasks[name]
        info = self._task_info.get(name, {})

        return {
            "name": name,
            "running": not task.done(),
            "cancelled": task.cancelled(),
            **info
        }

    def get_all_tasks_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all registered tasks.

        Returns:
            Dictionary mapping task names to status information
        """
        return {
            name: self.get_task_status(name)
            for name in self._tasks.keys()
        }

    def is_task_running(self, name: str) -> bool:
        """
        Check if a task is currently running.

        Args:
            name: Name of the task

        Returns:
            True if task exists and is running
        """
        task = self._tasks.get(name)
        return task is not None and not task.done()

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop all tasks."""
        await self.stop_all()


__all__ = ['BackgroundTaskManager']
