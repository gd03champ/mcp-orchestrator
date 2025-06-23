"""Dashboard web application for MCP Orchestrator."""

import os
import flask
from flask import (
    Flask, Blueprint, render_template, redirect, url_for,
    request, flash, jsonify, current_app, g, send_from_directory
)
import subprocess
import datetime

from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager
from orchestrator.container_manager import ContainerManager
from orchestrator.alb_manager import ALBManager
from orchestrator.dashboard.auth import bp as auth_bp, login_required, init_auth

# Set up logger
logger = setup_logging(__name__)

# Create blueprint
bp = Blueprint('dashboard', __name__)

# App factory
def create_app(config_manager, container_manager, alb_manager):
    """Create Flask application.
    
    Args:
        config_manager: The configuration manager instance
        container_manager: The container manager instance
        alb_manager: The ALB manager instance
    
    Returns:
        Flask application
    """
    # Create Flask app
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8)
    )
    
    # Setup authentication
    init_auth(config_manager)
    app.register_blueprint(auth_bp)
    
    # Store managers
    app.config['config_manager'] = config_manager
    app.config['container_manager'] = container_manager
    app.config['alb_manager'] = alb_manager
    
    # Register dashboard blueprint
    app.register_blueprint(bp)
    
    # Root redirects to dashboard
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))
    
    # Setup monitoring path
    dashboard_path = config_manager.get_setting('dashboard', 'path', '/monitor')
    app.config['APPLICATION_ROOT'] = dashboard_path
    
    return app

@bp.before_request
@login_required
def before_request():
    """Make sure managers are available to all requests."""
    g.config_manager = current_app.config['config_manager']
    g.container_manager = current_app.config['container_manager']
    g.alb_manager = current_app.config['alb_manager']

@bp.route('/')
@login_required
def index():
    """Dashboard index page."""
    # Get container information
    containers = g.container_manager.get_all_container_info()
    
    # Calculate stats
    mcp_servers = g.config_manager.get_mcp_servers()
    
    stats = {
        'total': len(mcp_servers),
        'running': 0,
        'stopped': 0,
        'disabled': 0
    }
    
    for server_id, config in mcp_servers.items():
        if config.get('disabled', False):
            stats['disabled'] += 1
            continue
            
        container_info = containers.get(server_id, {})
        if container_info.get('exists', False):
            if container_info.get('running', False):
                stats['running'] += 1
            else:
                stats['stopped'] += 1
                
    return render_template('dashboard/index.html', 
                          containers=containers, 
                          container_stats=stats)

@bp.route('/containers')
@login_required
def containers():
    """Container details page."""
    # Get container information
    containers = g.container_manager.get_all_container_info()
    
    # Get MCP server configurations
    mcp_servers = g.config_manager.get_mcp_servers()
    
    return render_template('dashboard/containers.html', 
                          containers=containers,
                          mcp_servers=mcp_servers)

@bp.route('/alb')
@login_required
def alb():
    """ALB configuration page."""
    # Get container information with port allocations
    containers = g.container_manager.get_all_container_info()
    
    return render_template('dashboard/alb.html', containers=containers)

@bp.route('/logs')
@login_required
def logs():
    """Logs page."""
    # Get recent logs (dummy implementation for now)
    logs = ["Log viewing not implemented yet"]
    
    return render_template('dashboard/logs.html', logs=logs)

@bp.route('/container/<server_id>/start')
@login_required
def start_container(server_id):
    """Start a container."""
    # Get server config
    server_config = g.config_manager.get_mcp_server(server_id)
    if not server_config:
        flash(f"Server {server_id} not found in configuration")
        return redirect(url_for('dashboard.index'))
    
    # Create container
    container_id = g.container_manager.create_container(server_id, server_config)
    if container_id:
        flash(f"Container for {server_id} started successfully")
        
        # Set up ALB after container starts
        g.alb_manager.setup_alb_for_server(server_id)
    else:
        flash(f"Failed to start container for {server_id}")
    
    return redirect(url_for('dashboard.index'))

@bp.route('/container/<server_id>/stop')
@login_required
def stop_container(server_id):
    """Stop a container."""
    if g.container_manager.stop_container(server_id):
        flash(f"Container for {server_id} stopped successfully")
    else:
        flash(f"Failed to stop container for {server_id}")
    
    return redirect(url_for('dashboard.index'))

@bp.route('/container/<server_id>/restart')
@login_required
def restart_container(server_id):
    """Restart a container."""
    if g.container_manager.restart_container(server_id):
        flash(f"Container for {server_id} restarted successfully")
    else:
        flash(f"Failed to restart container for {server_id}")
    
    return redirect(url_for('dashboard.index'))

@bp.route('/container/<server_id>/create')
@login_required
def create_container(server_id):
    """Create a container."""
    # Get server config
    server_config = g.config_manager.get_mcp_server(server_id)
    if not server_config:
        flash(f"Server {server_id} not found in configuration")
        return redirect(url_for('dashboard.index'))
    
    # Create container
    container_id = g.container_manager.create_container(server_id, server_config)
    if container_id:
        flash(f"Container for {server_id} created successfully")
        
        # Set up ALB after container is created
        g.alb_manager.setup_alb_for_server(server_id)
    else:
        flash(f"Failed to create container for {server_id}")
    
    return redirect(url_for('dashboard.index'))

@bp.route('/sync')
@login_required
def sync():
    """Synchronize containers and ALB with configuration."""
    # Sync containers
    container_results = g.container_manager.sync_containers()
    
    # Sync ALB rules
    alb_results = g.alb_manager.sync_alb()
    
    # Display results
    flash_messages = []
    
    if container_results['created']:
        flash_messages.append(f"Created containers: {', '.join(container_results['created'])}")
    
    if container_results['updated']:
        flash_messages.append(f"Updated containers: {', '.join(container_results['updated'])}")
    
    if container_results['stopped']:
        flash_messages.append(f"Stopped containers: {', '.join(container_results['stopped'])}")
    
    if container_results['errors']:
        flash_messages.append(f"Container errors: {', '.join(container_results['errors'])}")
    
    if alb_results['created']:
        flash_messages.append(f"Created ALB rules: {', '.join(alb_results['created'])}")
    
    if alb_results['updated']:
        flash_messages.append(f"Updated ALB rules: {', '.join(alb_results['updated'])}")
    
    if alb_results['deleted']:
        flash_messages.append(f"Deleted ALB rules: {', '.join(alb_results['deleted'])}")
    
    if alb_results['errors']:
        flash_messages.append(f"ALB errors: {', '.join(alb_results['errors'])}")
    
    if not flash_messages:
        flash("Synchronization completed. No changes were needed.")
    else:
        for msg in flash_messages:
            flash(msg)
    
    return redirect(url_for('dashboard.index'))

def run_dashboard(config_manager, container_manager, alb_manager, host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard application.
    
    Args:
        config_manager: The configuration manager instance
        container_manager: The container manager instance
        alb_manager: The ALB manager instance
        host: Host to bind to
        port: Port to bind to
        debug: Whether to run in debug mode
    """
    app = create_app(config_manager, container_manager, alb_manager)
    app.run(host=host, port=port, debug=debug)
