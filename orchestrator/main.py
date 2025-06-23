#!/usr/bin/env python3
"""Main entry point for MCP Orchestrator."""

import os
import sys
import time
import signal
import threading
import argparse
import logging

from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager
from orchestrator.container_manager import ContainerManager
from orchestrator.alb_manager import ALBManager
from orchestrator.dashboard.app import run_dashboard

# Set up logger
logger = setup_logging("mcp-orchestrator", level=logging.INFO)

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    """Handle termination signals."""
    global shutdown_requested
    logger.info(f"Received signal {sig}, initiating graceful shutdown")
    shutdown_requested = True

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='MCP Docker Orchestrator - A service that manages MCP servers as Docker containers and configures AWS ALB routing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python main.py
  
  # Run with custom config files
  python main.py --config /path/to/mcp.config.json --settings /path/to/settings.conf
  
  # Run once and exit (for testing)
  python main.py --one-shot
  
  # Run without dashboard
  python main.py --no-dashboard
        """
    )
    parser.add_argument('--config', default='mcp.config.json',
                        help='Path to MCP configuration file (default: mcp.config.json)')
    parser.add_argument('--settings', default='settings.conf',
                        help='Path to settings file (default: settings.conf)')
    parser.add_argument('--no-dashboard', action='store_true',
                        help='Disable web dashboard')
    parser.add_argument('--dashboard-port', type=int, default=5000,
                        help='Port for web dashboard (default: 5000)')
    parser.add_argument('--one-shot', action='store_true',
                        help='Run once and exit (for testing)')
    parser.add_argument('--version', action='version', version='MCP Docker Orchestrator v1.0.0')
    return parser.parse_args()

def reconciliation_loop(config_manager, container_manager, alb_manager, interval=60):
    """Run the reconciliation loop to keep resources in sync.
    
    Args:
        config_manager: The configuration manager instance
        container_manager: The container manager instance
        alb_manager: The ALB manager instance
        interval: Sleep interval between reconciliation cycles
    """
    global shutdown_requested
    
    while not shutdown_requested:
        try:
            # Reload configuration
            config_manager.load_config()
            
            # Synchronize containers
            logger.info("Running container reconciliation")
            container_results = container_manager.sync_containers()
            logger.info(f"Container sync complete: "
                       f"{len(container_results['created'])} created, "
                       f"{len(container_results['updated'])} updated, "
                       f"{len(container_results['stopped'])} stopped")
            
            if container_results['errors']:
                logger.error(f"Container sync errors: {container_results['errors']}")
                
            # Synchronize ALB resources
            logger.info("Running ALB reconciliation")
            alb_results = alb_manager.sync_alb()
            logger.info(f"ALB sync complete: "
                       f"{len(alb_results['created'])} created, "
                       f"{len(alb_results['updated'])} updated, "
                       f"{len(alb_results['deleted'])} deleted")
                       
            if alb_results['errors']:
                logger.error(f"ALB sync errors: {alb_results['errors']}")
                
        except Exception as e:
            logger.error(f"Error in reconciliation loop: {str(e)}", exc_info=True)
            
        # If this is a one-shot run, exit
        if interval <= 0:
            logger.info("One-shot run complete, exiting")
            break
            
        # Sleep until next reconciliation cycle
        for _ in range(interval):
            if shutdown_requested:
                break
            time.sleep(1)

def run_dashboard_thread(config_manager, container_manager, alb_manager, port=5000):
    """Run the dashboard in a separate thread.
    
    Args:
        config_manager: The configuration manager instance
        container_manager: The container manager instance
        alb_manager: The ALB manager instance
        port: Port for web dashboard
    """
    try:
        logger.info(f"Starting dashboard on port {port}")
        run_dashboard(
            config_manager=config_manager,
            container_manager=container_manager,
            alb_manager=alb_manager,
            port=port
        )
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}", exc_info=True)

def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Parse command line arguments
    args = parse_args()
    
    try:
        # Initialize managers
        logger.info("Initializing MCP Orchestrator")
        config_manager = ConfigManager(
            mcp_config_path=args.config,
            settings_path=args.settings
        )
        
        container_manager = ContainerManager(config_manager)
        alb_manager = ALBManager(config_manager, container_manager)
        
        # Start dashboard in a separate thread if enabled
        dashboard_thread = None
        if not args.no_dashboard:
            dashboard_thread = threading.Thread(
                target=run_dashboard_thread,
                args=(config_manager, container_manager, alb_manager, args.dashboard_port),
                daemon=True
            )
            dashboard_thread.start()
        
        # Run reconciliation loop
        interval = 0 if args.one_shot else int(config_manager.get_setting(
            "service", "reconciliation_interval_seconds", 60
        ))
        reconciliation_loop(config_manager, container_manager, alb_manager, interval)
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
        
    logger.info("MCP Orchestrator shutting down")
    sys.exit(0)

if __name__ == "__main__":
    main()
