# Maan - معا | Collaborative Coding Platform

<div align="center">

![Maan Logo](https://img.shields.io/badge/Maan-معا-007acc?style=for-the-badge&logo=visual-studio-code)

**Real-time collaborative coding platform inspired by VS Code**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-4.5+-010101?style=flat&logo=socket.io&logoColor=white)](https://socket.io/)
[![Monaco Editor](https://img.shields.io/badge/Monaco-0.38-007ACC?style=flat&logo=visual-studio-code&logoColor=white)](https://microsoft.github.io/monaco-editor/)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat)](LICENSE)

</div>

---

## Overview

**Maan** (Arabic: معا, meaning "together") is a powerful real-time collaborative coding platform that enables teams to code together seamlessly. Built with a VS Code-inspired interface, Maan provides an intuitive environment for pair programming, code reviews, and team collaboration.

### Key Features

- **Real-time Collaboration** - See cursors, edits, and changes as they happen
- **Multi-user Sessions** - Support for up to 5 developers per session
- **VS Code Interface** - Familiar, professional IDE experience
- **File Management** - Full CRUD operations on files and folders
- **Built-in Chat** - Team communication without leaving the editor
- **Admin Controls** - Approval system for joins and file saves
- **GitHub Integration** - Clone projects directly from GitHub
- **Flexible Authentication** - Support for registered and anonymous users
- **Live Cursors** - See where team members are working in real-time
- **Admin Dashboard** - Comprehensive platform management

---

## Architecture

### Technology Stack

#### Backend
- **Flask** - Web framework
- **Flask-SocketIO** - Real-time bidirectional communication
- **SQLAlchemy** - Database ORM
- **SQLite** - Database (easily switchable to PostgreSQL/MySQL)
- **GitPython** - GitHub repository cloning

#### Frontend
- **Monaco Editor** - Microsoft's VS Code editor engine
- **Socket.IO Client** - Real-time communication
- **Vanilla JavaScript** - No framework dependencies
- **Font Awesome** - Icon library
- **Inter Font** - Modern typography

### System Architecture

```
┌─────────────────┐
│   Web Browser   │
│  (Monaco Editor)│
└────────┬────────┘
         │ WebSocket
         │ (Socket.IO)
┌────────▼────────┐
│  Flask Server   │
│  + SocketIO     │
├─────────────────┤
│  SQLAlchemy     │
└────────┬────────┘
         │
┌────────▼────────┐
│  SQLite DB      │
└─────────────────┘
```

---

## Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git
- Modern web browser (Chrome, Firefox, Edge, Safari)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/maan.git
   cd maan
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install flask flask-cors flask-socketio flask-sqlalchemy gitpython werkzeug
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the platform**
   Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

---

## Usage Guide

### For Regular Users

#### 1. Registration & Login
- Navigate to `http://localhost:5000`
- Create an account or login with existing credentials
- Anonymous users can join sessions directly via session links

#### 2. Creating a Project
- Click **"New Project"** from the dashboard
- Enter project name
- Optionally provide a GitHub URL to clone
- Share the generated session link with team members

#### 3. Joining a Session
- Click on a session link or navigate from dashboard
- Wait for admin approval (if required)
- Start coding collaboratively

#### 4. Collaborative Features
- **Live Editing**: Changes appear instantly for all users
- **Cursor Tracking**: See where teammates are working
- **File Operations**: Create, rename, delete files (admin only)
- **Chat**: Communicate without leaving the editor
- **Save Files**: Request approval for saving (non-admins)

### For Administrators

#### Project Management
- Create and manage multiple projects
- Control user access with approval system
- Kick users from sessions
- Close sessions when needed

#### Admin Dashboard
- Access via the **"Admin Dashboard"** button
- View all users and projects
- Promote users to admin
- Delete users and manage platform

---

## Features in Detail

### Real-time Collaboration
- **Operational Transformation**: Ensures conflict-free collaborative editing
- **Cursor Synchronization**: See live cursor positions with color-coded labels
- **Change Propagation**: Instant text updates across all clients

### File Management
- **Tree View**: Hierarchical file and folder navigation
- **Context Menus**: Right-click operations for files/folders
- **GitHub Cloning**: Import existing repositories
- **Safe Path Handling**: Security measures against path traversal

### User Management
- **Authentication**: Secure password hashing with Werkzeug
- **Session Tracking**: Unique session IDs for reconnection handling
- **User Colors**: Automatic color assignment for visual identification
- **Approval System**: Admin control over joins and saves

### Communication
- **Built-in Chat**: Real-time messaging with color-coded usernames
- **System Notifications**: Automated messages for user events
- **Visual Indicators**: User presence dots on file tree

---

## Configuration

### Environment Variables

Create a `.env` file (optional) for custom configuration:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URI=sqlite:///maan.db
MAX_USERS_PER_SESSION=5
WORKSPACE_BASE_PATH=./workspaces
```

### Database Configuration

By default, Maan uses SQLite. To use PostgreSQL or MySQL:

```python
# In app.py, change:
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/maan'
# or
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://user:pass@localhost/maan'
```

---

## Project Structure

```
maan/
├── app.py                 # Main Flask application
├── templates/
│   ├── login.html         # Login/Registration page
│   ├── dashboard.html     # User dashboard
│   ├── session.html       # Collaborative editor
│   └── admin.html         # Admin dashboard
├── workspaces/            # User project workspaces
├── instance/
├── └── maan.db            # SQLite database
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

---

## Security Features

- **Password Hashing**: Werkzeug secure password hashing
- **Path Validation**: Prevention of directory traversal attacks
- **Session Management**: Secure session handling with Flask
- **CSRF Protection**: Built-in Flask security features
- **Access Control**: Role-based permissions (Admin/User)

---

## Known Issues & Limitations

1. **File Size**: Large files may cause performance issues
2. **Binary Files**: Not optimized for binary file editing
3. **Concurrent Saves**: Last-write-wins strategy
4. **Mobile Support**: Limited mobile browser support
5. **Scale**: Designed for small teams (5 users max per session)

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 for Python code
- Use meaningful commit messages
- Add comments for complex logic
- Test thoroughly before submitting PR

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Monaco Editor** - Microsoft's powerful code editor
- **Flask** - Lightweight and flexible web framework
- **Socket.IO** - Real-time communication library
- **Font Awesome** - Beautiful icon library
- **VS Code** - Design inspiration

---

## Star History

If you find this project useful, please consider giving it a star ⭐

