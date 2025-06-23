"""Authentication module for the MCP Orchestrator dashboard."""

import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager

# Set up logger
logger = setup_logging(__name__)

# Create blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')

def init_auth(config_manager):
    """Initialize the authentication module.
    
    Args:
        config_manager: The configuration manager instance
    """
    # Store config manager in the blueprint
    bp.config_manager = config_manager

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

@bp.before_app_request
def load_logged_in_user():
    """Load user information from the session."""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = user_id

@bp.route('/login', methods=('GET', 'POST'))
def login():
    """Handle user login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        error = None

        # Get configured username and password
        config_username = bp.config_manager.get_setting('dashboard', 'username', 'admin')
        config_password = bp.config_manager.get_setting('dashboard', 'password', 'changeme')

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif username != config_username or password != config_password:
            error = 'Incorrect username or password.'

        if error is None:
            # Store the user's id in the session
            session.clear()
            session['user_id'] = username
            logger.info(f"User {username} logged in")
            return redirect(url_for('dashboard.index'))

        flash(error)
        logger.warning(f"Failed login attempt for username: {username}")

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    """Handle user logout."""
    username = session.get('user_id')
    session.clear()
    if username:
        logger.info(f"User {username} logged out")
    return redirect(url_for('auth.login'))
