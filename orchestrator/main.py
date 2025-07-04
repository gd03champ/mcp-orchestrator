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
from orchestrator.compose_manager import ComposeManager
from orchestrator.alb_manager import ALBManager
from orchestrator.dashboard.app import run_dashboard

# Remove the container_manager import as we use compose_manager instead

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
  python main.py --compose /path/to/mcp-compose.yaml --settings /path/to/settings.conf
  
  # Run once and exit (for testing)
  python main.py --one-shot
  
  # Run without dashboard
  python main.py --no-dashboard
        """
    )
    parser.add_argument('--compose', default='mcp-compose.yaml',
                        help='Path to MCP Docker Compose file (default: mcp-compose.yaml)')
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

def reconciliation_loop(config_manager, compose_manager, alb_manager, interval=60):
    """Run the reconciliation loop to keep resources in sync.
    
    Args:
        config_manager: The configuration manager instance
        compose_manager: The Docker Compose manager instance
        alb_manager: The ALB manager instance
        interval: Sleep interval between reconciliation cycles
    """
    global shutdown_requested
    
    while not shutdown_requested:
        try:
            # Reload configuration
            config_manager.load_config()
            
            # Synchronize services
            logger.info("Running service reconciliation")
            service_results = compose_manager.sync_services()
            logger.info(f"Service sync complete: "
                       f"{len(service_results['created'])} created, "
                       f"{len(service_results['updated'])} updated, "
                       f"{len(service_results['stopped'])} stopped")
            
            if service_results['errors']:
                logger.error(f"Service sync errors: {service_results['errors']}")
                
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

def run_dashboard_thread(config_manager, compose_manager, alb_manager, port=5000):
    """Run the dashboard in a separate thread.
    
    Args:
        config_manager: The configuration manager instance
        compose_manager: The Docker Compose manager instance
        alb_manager: The ALB manager instance
        port: Port for web dashboard
    """
    try:
        logger.info(f"Starting dashboard on port {port}")
        run_dashboard(
            config_manager=config_manager,
            container_manager=compose_manager,  # Dashboard code will use container_manager interface
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
        # Initialize config manager
        logger.info("Initializing MCP Orchestrator")
        config_manager = ConfigManager(
            compose_path=args.compose,
            settings_path=args.settings
        )
        
        # Initialize managers
        compose_manager = ComposeManager(config_manager)
        alb_manager = ALBManager(config_manager, compose_manager)
        
        # Start dashboard in a separate thread if enabled
        dashboard_thread = None
        if not args.no_dashboard:
            dashboard_thread = threading.Thread(
                target=run_dashboard_thread,
                args=(config_manager, compose_manager, alb_manager, args.dashboard_port),
                daemon=True
            )
            dashboard_thread.start()
        
        # Run reconciliation loop
        interval = 0 if args.one_shot else int(config_manager.get_setting(
            "service", "reconciliation_interval_seconds", 60
        ))
        reconciliation_loop(config_manager, compose_manager, alb_manager, interval)
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
        
    logger.info("MCP Orchestrator shutting down")
    sys.exit(0)

if __name__ == "__main__":
    main()
