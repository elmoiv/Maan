import os
import sys
import json
import shutil
import secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import git
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///maan.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

WORKSPACE_BASE = os.path.abspath('./workspaces')
os.makedirs(WORKSPACE_BASE, exist_ok=True)

# ==================== Models ====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    session_id = db.Column(db.String(50), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    github_url = db.Column(db.String(300))
    workspace_path = db.Column(db.String(300))
    max_users = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)

class SessionUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    color = db.Column(db.String(7), nullable=False)
    current_file = db.Column(db.String(300))
    cursor_position = db.Column(db.String(50))
    is_anonymous = db.Column(db.Boolean, default=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ==================== Active Sessions Storage ====================
active_sessions = {}  # {session_id: {users: [], pending_approvals: []}}
user_colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2']

# ==================== Helper Functions ====================
def get_workspace_dir(session_id):
    return os.path.join(WORKSPACE_BASE, session_id)

def get_file_tree(path):
    tree = []
    try:
        with os.scandir(path) as entries:
            sorted_entries = sorted(entries, key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in sorted_entries:
                if entry.name.startswith('.'):
                    continue
                item = {
                    'name': entry.name,
                    'path': os.path.relpath(entry.path, path).replace('\\', '/'),
                    'is_dir': entry.is_dir()
                }
                if entry.is_dir():
                    item['children'] = get_file_tree(entry.path)
                tree.append(item)
    except PermissionError:
        pass
    return tree

def is_safe_path(workspace_path, relative_path):
    full_path = os.path.abspath(os.path.join(workspace_path, relative_path))
    return os.path.commonprefix([full_path, workspace_path]) == workspace_path

def assign_color():
    import random
    return random.choice(user_colors)

# ==================== Authentication Routes ====================
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()
    
    session['user_id'] = user.id
    return jsonify({'status': 'success', 'user': {'id': user.id, 'username': user.username}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    session['user_id'] = user.id
    return jsonify({'status': 'success', 'user': {'id': user.id, 'username': user.username, 'is_admin': user.is_admin}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'success'})

# ==================== Project Routes ====================
@app.route('/api/projects/create', methods=['POST'])
def create_project():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    name = data.get('name')
    github_url = data.get('github_url')
    
    session_id = secrets.token_urlsafe(16)
    workspace_path = get_workspace_dir(session_id)
    os.makedirs(workspace_path, exist_ok=True)
    
    # Clone from GitHub if URL provided
    if github_url:
        try:
            git.Repo.clone_from(github_url, workspace_path)
        except Exception as e:
            return jsonify({'error': f'Failed to clone: {str(e)}'}), 400
    
    project = Project(
        name=name,
        session_id=session_id,
        admin_id=session['user_id'],
        github_url=github_url,
        workspace_path=workspace_path
    )
    db.session.add(project)
    db.session.commit()
    
    active_sessions[session_id] = {'users': [], 'pending_approvals': []}
    
    return jsonify({
        'status': 'success',
        'session_id': session_id,
        'join_url': f'/session/{session_id}'
    })

@app.route('/api/projects/my', methods=['GET'])
def get_my_projects():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    projects = Project.query.filter_by(admin_id=session['user_id'], active=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'session_id': p.session_id,
        'github_url': p.github_url,
        'created_at': p.created_at.isoformat()
    } for p in projects])

@app.route('/api/projects/<session_id>/info', methods=['GET'])
def get_project_info(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    return jsonify({
        'name': project.name,
        'session_id': project.session_id,
        'max_users': project.max_users,
        'active': project.active
    })

# ==================== File Operations ====================
@app.route('/api/session/<session_id>/files', methods=['GET'])
def list_files(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    tree = get_file_tree(project.workspace_path)
    return jsonify({'name': project.name, 'children': tree})

@app.route('/api/session/<session_id>/files/content', methods=['GET'])
def get_file_content(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    path = request.args.get('path')
    if not path or not is_safe_path(project.workspace_path, path):
        return jsonify({'error': 'Invalid path'}), 400
    
    full_path = os.path.join(project.workspace_path, path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        mtime = os.path.getmtime(full_path)

        return jsonify({'content': content, 'mtime': mtime})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<session_id>/files/save', methods=['POST'])
def save_file(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    data = request.json
    path = data.get('path')
    content = data.get('content')
    user_info = data.get('user_info')
    
    # Check if user is admin
    if 'user_id' in session and session['user_id'] == project.admin_id:
        # Admin can save directly
        if not is_safe_path(project.workspace_path, path):
            return jsonify({'error': 'Invalid path'}), 400
        
        full_path = os.path.join(project.workspace_path, path)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        mtime = os.path.getmtime(full_path)
        
        # Notify all users with content
        socketio.emit('file_saved', {
            'path': path, 
            'user': user_info,
            'content': content,
            'mtime': mtime
        }, room=session_id)
        return jsonify({'status': 'success'})
    else:
        # Request approval (same as before)
        if session_id not in active_sessions:
            active_sessions[session_id] = {'users': [], 'pending_approvals': []}
        
        approval_id = secrets.token_hex(8)
        active_sessions[session_id]['pending_approvals'].append({
            'id': approval_id,
            'type': 'save',
            'path': path,
            'content': content,
            'user': user_info
        })
        
        socketio.emit('approval_request', {
            'id': approval_id,
            'type': 'save',
            'path': path,
            'user': user_info
        }, room=f"{session_id}_admin")
        
        return jsonify({'status': 'pending_approval'})

@app.route('/api/session/<session_id>/files/create', methods=['POST'])
def create_file(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if 'user_id' not in session or session['user_id'] != project.admin_id:
        return jsonify({'error': 'Only admin can create files'}), 403
    
    data = request.json
    path = data.get('path')
    is_dir = data.get('is_dir', False)
    
    if not is_safe_path(project.workspace_path, path):
        return jsonify({'error': 'Invalid path'}), 400
    
    full_path = os.path.join(project.workspace_path, path)
    
    try:
        if is_dir:
            os.makedirs(full_path, exist_ok=True)
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write('')
        
        socketio.emit('file_created', {'path': path, 'is_dir': is_dir}, room=session_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<session_id>/files/delete', methods=['DELETE'])
def delete_file(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if 'user_id' not in session or session['user_id'] != project.admin_id:
        return jsonify({'error': 'Only admin can delete files'}), 403
    
    path = request.args.get('path')
    if not is_safe_path(project.workspace_path, path):
        return jsonify({'error': 'Invalid path'}), 400
    
    full_path = os.path.join(project.workspace_path, path)
    
    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        
        socketio.emit('file_deleted', {'path': path}, room=session_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<session_id>/files/rename', methods=['POST'])
def rename_file(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if 'user_id' not in session or session['user_id'] != project.admin_id:
        return jsonify({'error': 'Only admin can rename files'}), 403
    
    data = request.json
    old_path = data.get('old_path')
    new_path = data.get('new_path')
    
    if not is_safe_path(project.workspace_path, old_path) or not is_safe_path(project.workspace_path, new_path):
        return jsonify({'error': 'Invalid path'}), 400
    
    old_full = os.path.join(project.workspace_path, old_path)
    new_full = os.path.join(project.workspace_path, new_path)
    
    try:
        os.rename(old_full, new_full)
        socketio.emit('file_renamed', {'old_path': old_path, 'new_path': new_path}, room=session_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Admin Routes ====================

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/session/<session_id>')
def session_page(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project or not project.active:
        return "Session not found or inactive", 404
    return render_template('session.html', session_id=session_id)

@app.route('/admin/dashboard')
def admin_dashboard_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    if not user or not user.is_admin:
        return "Unauthorized", 403
    return render_template('admin.html')

@app.route('/api/admin/dashboard', methods=['GET'])
def admin_dashboard():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return jsonify({'error': 'Not authorized'}), 403
    
    all_users = User.query.all()
    all_projects = Project.query.all()
    
    stats = {
        'total_users': len(all_users),
        'total_projects': len(all_projects),
        'active_sessions': len([p for p in all_projects if p.active])
    }
    
    return jsonify({
        'stats': stats,
        'users': [{'id': u.id, 'username': u.username, 'email': u.email} for u in all_users],
        'projects': [{'id': p.id, 'name': p.name, 'session_id': p.session_id} for p in all_projects]
    })

@app.route('/api/admin/make-admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        return jsonify({'error': 'Not authorized'}), 403
    
    user = User.query.get(user_id)
    if user:
        user.is_admin = True
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/delete-user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        return jsonify({'error': 'Not authorized'}), 403
    
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/kick-user/<session_id>/<sid>', methods=['POST'])
def kick_user(session_id, sid):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    project = Project.query.filter_by(session_id=session_id).first()
    if not project or session['user_id'] != project.admin_id:
        return jsonify({'error': 'Not authorized'}), 403
    
    # Remove user from active sessions immediately
    if session_id in active_sessions:
        user = next((u for u in active_sessions[session_id]['users'] if u['sid'] == sid), None)
        if user:
            active_sessions[session_id]['users'] = [
                u for u in active_sessions[session_id]['users'] if u['sid'] != sid
            ]
            # Notify all users that this user left
            socketio.emit('user_left', {
                'sid': sid,
                'username': user['username']
            }, room=session_id)
    
    socketio.emit('kicked', {'message': 'You have been removed from the session'}, room=sid)
    return jsonify({'status': 'success'})

@app.route('/api/admin/close-session/<session_id>', methods=['POST'])
def close_session(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    project = Project.query.filter_by(session_id=session_id).first()
    if not project or session['user_id'] != project.admin_id:
        return jsonify({'error': 'Not authorized'}), 403
    
    project.active = False
    db.session.commit()
    socketio.emit('session_closed', {'message': 'Session has been closed'}, room=session_id)
    return jsonify({'status': 'success'})

@app.route('/api/session/<session_id>/files', methods=['GET'])
def list_files_with_path(session_id):
    project = Project.query.filter_by(session_id=session_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    path = request.args.get('path', '')
    workspace_path = project.workspace_path
    
    if path and is_safe_path(workspace_path, path):
        target_path = os.path.join(workspace_path, path)
    else:
        target_path = workspace_path
    
    tree = get_file_tree(target_path)
    return jsonify({'name': os.path.basename(target_path), 'children': tree})

# ==================== WebSocket Events ====================
@socketio.on('join_session')
def handle_join_session(data):
    session_id = data['session_id']
    username = data['username']
    is_anonymous = data.get('is_anonymous', True)
    user_session_id = data.get('sessionId')
    
    project = Project.query.filter_by(session_id=session_id).first()
    if not project or not project.active:
        emit('error', {'message': 'Session not found or inactive'})
        return
    
    if session_id not in active_sessions:
        active_sessions[session_id] = {'users': [], 'pending_approvals': []}
    
    # Check if user already exists (reconnection)
    existing_user = None
    for user in active_sessions[session_id]['users']:
        if user.get('sessionId') == user_session_id:
            existing_user = user
            break
    
    # Check if user has pending approval (reload during pending state)
    pending_approval = None
    for approval in active_sessions[session_id]['pending_approvals']:
        if approval.get('sessionId') == user_session_id and approval.get('type') == 'join':
            pending_approval = approval
            break
    
    # Check if user is admin
    is_user_admin = 'user_id' in session and session['user_id'] == project.admin_id
    
    if pending_approval:
        # User reloaded while pending approval - update their sid and tell them to wait again
        pending_approval['sid'] = request.sid
        emit('waiting_approval', {'message': 'Waiting for admin approval...'})
        
    elif existing_user:
        # Reconnection - update socket ID
        existing_user['sid'] = request.sid
        user_data = existing_user
        join_room(session_id)
        
        if is_user_admin:
            join_room(f"{session_id}_admin")
            user_data['is_admin'] = True
        
        emit('user_connected', {'user': user_data})
        emit('session_state', {'users': active_sessions[session_id]['users']})
        
    elif is_user_admin:
        # Admin joins directly without approval
        if len(active_sessions[session_id]['users']) >= project.max_users:
            emit('error', {'message': 'Session is full'})
            return
        
        color = assign_color()
        user_data = {
            'sid': request.sid,
            'username': username,
            'color': color,
            'current_file': None,
            'is_anonymous': is_anonymous,
            'sessionId': user_session_id,
            'is_admin': True
        }
        active_sessions[session_id]['users'].append(user_data)
        
        join_room(session_id)
        join_room(f"{session_id}_admin")
        
        emit('user_connected', {'user': user_data})
        emit('user_joined', {
            'username': username,
            'color': user_data['color'],
            'user': user_data,
            'users': active_sessions[session_id]['users']
        }, room=session_id)
        
    else:
        # Non-admin requires approval
        if len(active_sessions[session_id]['users']) >= project.max_users:
            emit('error', {'message': 'Session is full'})
            return
        
        # Check if this user already has a pending approval (shouldn't happen but just in case)
        existing_pending = next((a for a in active_sessions[session_id]['pending_approvals'] 
                                if a.get('sessionId') == user_session_id and a.get('type') == 'join'), None)
        
        if existing_pending:
            # Update the sid
            existing_pending['sid'] = request.sid
            emit('waiting_approval', {'message': 'Waiting for admin approval...'})
        else:
            # Create new approval request
            approval_id = secrets.token_hex(8)
            active_sessions[session_id]['pending_approvals'].append({
                'id': approval_id,
                'type': 'join',
                'username': username,
                'is_anonymous': is_anonymous,
                'sessionId': user_session_id,
                'sid': request.sid
            })
            
            # Notify admin
            emit('join_approval_request', {
                'id': approval_id,
                'username': username
            }, room=f"{session_id}_admin")
            
            # Tell user to wait
            emit('waiting_approval', {'message': 'Waiting for admin approval...'})


@socketio.on('join_approval_response')
def handle_join_approval_response(data):
    session_id = data['session_id']
    approval_id = data['approval_id']
    approved = data['approved']
    
    if session_id not in active_sessions:
        return
    
    approval = next((a for a in active_sessions[session_id]['pending_approvals'] 
                     if a['id'] == approval_id and a['type'] == 'join'), None)
    if not approval:
        return
    
    if approved:
        project = Project.query.filter_by(session_id=session_id).first()
        
        # Check max users again
        if len(active_sessions[session_id]['users']) >= project.max_users:
            emit('error', {'message': 'Session is full'}, room=approval['sid'])
            active_sessions[session_id]['pending_approvals'] = [
                a for a in active_sessions[session_id]['pending_approvals'] 
                if a['id'] != approval_id
            ]
            return
        
        # Add user to session
        color = assign_color()
        user_data = {
            'sid': approval['sid'],
            'username': approval['username'],
            'color': color,
            'current_file': None,
            'is_anonymous': approval['is_anonymous'],
            'sessionId': approval['sessionId'],
            'is_admin': False
        }
        active_sessions[session_id]['users'].append(user_data)
        
        # CRITICAL: Make the user actually join the Socket.IO room
        socketio.server.enter_room(approval['sid'], session_id)
        
        # Tell user they're approved with their user data
        emit('join_approved', {'user': user_data}, room=approval['sid'])
        
        # Send them the current session state with all users
        emit('session_state', {'users': active_sessions[session_id]['users']}, room=approval['sid'])
        
        # Notify all users (including the newly joined user)
        emit('user_joined', {
            'username': approval['username'],
            'color': user_data['color'],
            'user': user_data,
            'users': active_sessions[session_id]['users']
        }, room=session_id)
    else:
        emit('join_rejected', {'message': 'Your request to join was denied'}, 
             room=approval['sid'])
    
    # Remove from pending
    active_sessions[session_id]['pending_approvals'] = [
        a for a in active_sessions[session_id]['pending_approvals'] 
        if a['id'] != approval_id
    ]

@socketio.on('leave_session')
def handle_leave_session(data):
    session_id = data['session_id']
    if session_id in active_sessions:
        user = next((u for u in active_sessions[session_id]['users'] if u['sid'] == request.sid), None)
        active_sessions[session_id]['users'] = [
            u for u in active_sessions[session_id]['users'] if u['sid'] != request.sid
        ]
        leave_room(session_id)
        if user:
            emit('user_left', {'sid': request.sid, 'username': user['username']}, room=session_id)

@socketio.on('cursor_move')
def handle_cursor_move(data):
    session_id = data['session_id']
    # Get user data to include color
    if session_id in active_sessions:
        user = next((u for u in active_sessions[session_id]['users'] if u['sid'] == request.sid), None)
        if user:
            emit('cursor_update', {
                'sid': request.sid,
                'position': data['position'],
                'file': data['file'],
                'color': user['color'],
                'username': user['username']
            }, room=session_id, include_self=False)

@socketio.on('file_change')
def handle_file_change(data):
    session_id = data['session_id']
    emit('content_update', {
        'sid': request.sid,
        'changes': data['changes'],
        'file': data['file'],
        'version': data.get('version', 0)
    }, room=session_id, include_self=False)

@socketio.on('file_open')
def handle_file_open(data):
    session_id = data['session_id']
    file_path = data['file']
    
    if session_id in active_sessions:
        for user in active_sessions[session_id]['users']:
            if user['sid'] == request.sid:
                user['current_file'] = file_path
                break
    
    emit('user_file_change', {
        'sid': request.sid,
        'file': file_path
    }, room=session_id, include_self=True)

@socketio.on('chat_message')
def handle_chat_message(data):
    session_id = data['session_id']
    # Get user color from active sessions
    user_color = data.get('color', '#999')
    if session_id in active_sessions:
        user = next((u for u in active_sessions[session_id]['users'] if u['username'] == data['username']), None)
        if user:
            user_color = user['color']
    
    emit('chat_message', {
        'username': data['username'],
        'color': user_color,
        'message': data['message'],
        'timestamp': datetime.utcnow().isoformat()
    }, room=session_id)

@socketio.on('approval_response')
def handle_approval_response(data):
    session_id = data['session_id']
    approval_id = data['approval_id']
    approved = data['approved']
    
    if session_id not in active_sessions:
        return
    
    approval = next((a for a in active_sessions[session_id]['pending_approvals'] if a['id'] == approval_id), None)
    if not approval:
        return
    
    if approved and approval['type'] == 'save':
        project = Project.query.filter_by(session_id=session_id).first()
        if not is_safe_path(project.workspace_path, approval['path']):
            emit('error', {'message': 'Invalid path'})
            return
            
        full_path = os.path.join(project.workspace_path, approval['path'])
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(approval['content'])
            
            # Emit to ALL users with content so they can sync
            emit('file_saved', {
                'path': approval['path'], 
                'user': approval['user'],
                'content': approval['content'],
                'mtime': os.path.getmtime(full_path)
            }, room=session_id)
        except Exception as e:
            emit('error', {'message': f'Failed to save: {str(e)}'})
    
    active_sessions[session_id]['pending_approvals'] = [
        a for a in active_sessions[session_id]['pending_approvals'] if a['id'] != approval_id
    ]
    
    emit('approval_result', {
        'id': approval_id,
        'approved': approved
    }, room=session_id)

@socketio.on('disconnect')
def handle_disconnect():
    # Find and remove user from all sessions
    for session_id, session_data in active_sessions.items():
        user = next((u for u in session_data['users'] if u['sid'] == request.sid), None)
        if user:
            session_data['users'] = [u for u in session_data['users'] 
                                     if u['sid'] != request.sid]
            emit('user_left', {
                'sid': request.sid, 
                'username': user['username']
            }, room=session_id, include_self=False)
            break
        
        # Also remove from pending approvals
        session_data['pending_approvals'] = [
            a for a in session_data['pending_approvals'] 
            if a.get('sid') != request.sid
        ]

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', log_output=True, port=5000)