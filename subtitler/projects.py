import os
import time
from math import ceil
from enum import Enum
from uuid import uuid4
from flask import (
    current_app, 
    Blueprint, 
    redirect, 
    render_template, 
    request, 
    send_file, 
    abort,
    url_for
)
from flask_htmx import HTMX, make_response
from werkzeug.utils import secure_filename
from subtitler.db import get_db
from jinja2_fragments.flask import render_block
from subtitler.db import get_db, query_db
from subtitler.tasks.video import process
from subtitler.utils import VTT
from subtitler.utils.speech_interface import video_info
from subtitler.htmx import htmx

bp = Blueprint('projects', __name__, url_prefix='/')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@bp.route('/', methods=('GET', 'POST'))
def index():
    db = get_db()
    
    count = query_db("SELECT count(id) as count FROM project",() ,True)
    num_pages = ceil(count[0] / current_app.config['PAGE_SIZE'])

    try:
        page = int(request.args.get('page') or 1)
    except ValueError:
        page = 1

    if page < 1:
        page = 1

    if page > num_pages:
        page = num_pages
    
    pages = []
    
    for i in range(num_pages):
        pages.append(i+1)
    
    pagination = {
    'pages' : pages,
    'num_pages' : num_pages,
    'current_page' : page
    }

    projects = db.execute("SELECT * FROM project ORDER BY created DESC LIMIT ? OFFSET ?", (current_app.config['PAGE_SIZE'],current_app.config['PAGE_SIZE']*(page-1))).fetchall()    

    if htmx:
        return render_block('pages/projects.html', 'projects_block', projects = projects, pagination = pagination)
    return render_template('pages/projects.html', projects = projects, pagination = pagination)

@bp.route('/<int:id>', methods=('GET', 'PUT'))
def project(id):
    if not htmx:
        return "no direct access!", 500
    db = get_db()
    if request.method == "PUT":
        name = request.form['name']
        description = request.form['description'] or ""
        if name:    
            db.execute("UPDATE project SET name = ?, description = ? WHERE id = ?",(name,description,id))
            db.commit() 

    project = get_project_byId(id)
    if project == None: 
        if htmx:
            return "Project not found", 404
        abort(404)
    return render_block("pages/editor.html", "project_meta", project=project)


    

@bp.route('/<int:id>/editor', methods=('GET',))
def editor(id):
    try:
        id = int(id)
    except ValueError:
        abort(404)
    
    db = get_db()
    subtitles = db.execute("SELECT * from line WHERE project_id = ? ORDER BY start ASC", (id,)).fetchall()
    if(subtitles == None):
        abort(404)
    project = get_project_byId(id)
    if(project == None):
        abort(404)
    return render_template('pages/editor.html', project=project, subtitles=subtitles)

@bp.route('/<int:id>/edit', methods=('GET',))
def edit(id):
    project = get_project_byId(id)
    if project == None:
        abort(404)
    return redirect(url_for('projects.editor', id=id))

@bp.route('/<int:id>/edit_project_form', methods=('GET',))
def edit_project_form(id):
    project = get_project_byId(id)
    if htmx:
        if project == None:
            return "Project not found", 404
        return render_template('partials/project_edit_inline.html' , project=project)
    else:
        return "No direct access", 500

@bp.route('/<int:id>/delete', methods=('DELETE',))
def delete(id):
    id = int(id)
    project = get_project_byId(id)
    if htmx:
        db = get_db()
        db.execute("DELETE from project WHERE id = ?", (id,))
        db.commit()
        return make_response("", trigger = "project_update")
    return "",500

@bp.route('/<int:id>/project_row', methods=('GET', 'POST'))
def project_row(id):
    id = int(id)
    project = get_project_byId(id)
    return render_block("pages/projects.html", "project_row_block", project=project)

@bp.route('/<int:id>/vtt', methods=('GET',))
def vtt(id):
    lines = []
    project = get_project_byId(id)
    if project == None:
        if htmx:
            return "Project not found", 404
        abort(404)
    for subtitle in query_db("SELECT * from line WHERE project_id = ? ORDER BY start ASC", (id,)):
        line = VTT.Line(subtitle['text'], subtitle['start'], subtitle['end'])
        lines.append(line)
    att = request.args.get("att") == "True"
    file_name = os.path.splitext(project['filename'])[0]
    return send_file(VTT.from_buffer(lines), download_name=f'{file_name}.vtt', as_attachment=att)

@bp.route('/upload', methods=('GET', 'POST'))
def upload():
    if request.method == "POST":
        db = get_db()
        project_name = request.form['name']
        project_description = request.form['description']

        if not project_name:
            return 'No project name', 500
        
        if 'file' not in request.files:
            return 'No file part', 500
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            return 'No selected file', 500
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1]
            stored_filename =  f"{uuid4().__str__()}{ext}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
            file.save(filepath)
            info = video_info(filepath)
            if info is None:
                return 'Wrong video stream detected, check file!', 500
            
            # insert new project           
            try:
                res = db.execute(
                    "INSERT INTO project (filename, stored_filename, name, description, length) VALUES (?, ?, ?, ?, ?)",
                    (filename, stored_filename, project_name, project_description, info['duration']),
                )
                db.commit()
                enqueue_project(res.lastrowid)
            except db.IntegrityError:
                return 'updating database failed', 500
            else:
                return make_response("", trigger = "project_update" )

    return render_template("partials/upload_form.html")

@bp.route('/<int:id>/retry')
def retry(id):
    if enqueue_project(id) == None:
        if htmx:
            return make_response("", trigger = "project_updated")
        else:
            return "Process already finished or processing"
    return make_response("", trigger = "project_update")

@bp.route('/<int:id>/download_video')
def download(id):
    project = get_project_byId(id) 
    if project == None:
        return "File does not exist...", 500
    file = os.path.join(current_app.config["UPLOAD_FOLDER"], project['stored_filename'])
    att = request.args.get("att") == "True"
    return send_file(file, download_name = project['filename'], as_attachment=att)

@bp.route('/<int:id>/poster')
def poster(id):
    project = get_project_byId(id)
    if project == None:
        return "project does not exist...", 500
    try:
        original_filename = os.path.splitext(project['filename'])[0]
        original_filename = f"{original_filename}-thumb.png"
        filename = os.path.splitext(project['stored_filename'])[0]
        filename = f"{filename}-thumb.png"
        file = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        att = request.args.get("att") == "True"
        return send_file(file, download_name = original_filename, as_attachment=att)
    except FileNotFoundError:
        return send_file(file, as_attachment=att)


@bp.app_template_filter('duration')
def duration(seconds):
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

@bp.app_template_filter('label')
def label(status):
    label = {
        'queued':'label-secondary',
        'uploaded':'label-secondary',
        'extracting': 'label-secondary',
        'processing' : 'label-secondary',
        'transcribing': 'label-primary',
        'error':'label-error',
        'done':'label-success'
    }
    if label[status]:
        return label[status]
    return label['queued']

@bp.app_template_filter('busy')
def busy(status):
    return status in ["extracting","transcribing"]

def enqueue_project(id):
    db = get_db()
    project = get_project_byId(id)
    if project and project['status'] == "uploaded":
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], project['stored_filename'])
        db.execute("UPDATE project SET status = ? WHERE id = ?", ("enqueued", project['id'],))
        db.commit()
        return process.delay(id, filepath)
    return None

def get_project_byId(id):
    project = query_db("SELECT * FROM project WHERE id = ? ",(id,), True)
    return project
