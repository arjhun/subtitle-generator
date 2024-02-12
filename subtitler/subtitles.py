from subtitler.db import get_db, query_db
from subtitler.utils import VTT
from subtitler import htmx
from flask import (
   Blueprint, render_template, request, abort
)
from jinja2_fragments.flask import render_block
from flask_htmx import make_response

bp = Blueprint('subtitles', __name__, url_prefix='/subtitles')

@bp.route('/<int:id>/delete', methods=('DELETE',))
def delete(id):
    id = int(id)
    db = get_db()
    db.execute("DELETE from line WHERE id = ?", (id,))
    db.commit()
    return ""

@bp.route('/<int:id>', methods=('GET', 'PUT'))
def subtitle(id):
    db = get_db()
    if request.method == "PUT":
        
        text = request.form['text']
        
        try:
            start = round(float(request.form['start']),3)
            end = round(float(request.form['length']) + start,3)
        except ValueError:
            return "Wrong values", 500

        if start < 0 or end < start:
             return "Wrong values", 500

        if text:
            db.execute("UPDATE line SET text = ?, start = ?, end = ? WHERE id = ?",(text,start,end, id))
            db.commit() 

    subtitle = get_subtitle_byId(id)
    return render_block("pages/editor.html", "line_block", subtitle=subtitle)

@bp.route('/<int:id>/modify', methods=('PUT',))
def modify(id): 
    
    blocks = []
    
    try:
        cursor = int(request.form['cursor'])
        start = float(request.form['start'])
        end = float(request.form['length']) + start
    except ValueError:
        return "Wrong values", 500
    
    if start < 0 or end < start:
        return "Wrong values", 500

    text = request.form['text']
    chars = len(text)

    subtitle = get_subtitle_byId(id)
    
    if subtitle == None:
        if htmx:
            return "Subtitle not found", 404
        abort(404)
       
    if cursor > 0 and cursor < chars and request.form['action'] in ["split", "right", "left"]:

        db = get_db()
        total_s = end - start 
    
        # get the new time based on position of cursor in text
        time_at_cursor = round(start + total_s * cursor / chars,1)
        text_left = text[:cursor]
        text_right = text[cursor:]
        new_text = text

        if request.form['action'] == "split":
        
            new_text = VTT.create_text(sanitize_line(text_left))
            text_right = VTT.create_text(sanitize_line(text_right))
            # right side
            res = db.execute( "INSERT INTO line (project_id, start, end, text) VALUES (?, ?, ?, ?)", 
                        ( subtitle['project_id'], 
                            time_at_cursor,
                            end,
                            text_right )
                        )
            new_id = res.lastrowid
            db.execute( "UPDATE line SET text = ?, end = ? WHERE id=?", (new_text, time_at_cursor, id))
            blocks.append(subtitle_block(id))
            blocks.append(subtitle_block(new_id))
        
        elif request.form['action'] == "right":
            
            next_sub = query_db("SELECT * FROM line \
                                WHERE project_id = ? \
                                AND start >= ?\
                                AND id != ? \
                                ORDER BY start ASC \
                                LIMIT 1",
                                (subtitle['project_id'], 
                                 subtitle['start'], 
                                 subtitle['id']), True)
            
            new_text = VTT.create_text(sanitize_line(text_left))
            text_right = text_right + " " + next_sub['text']
            text_right = VTT.create_text(sanitize_line(text_right))
            db.execute( "UPDATE line SET text = ?, start = ? WHERE id = ?", (text_right, time_at_cursor, next_sub['id']))
            db.execute( "UPDATE line SET text = ?, end = ? WHERE id=?", (new_text, time_at_cursor, id))
            blocks.append(subtitle_block(id))
            blocks.append(subtitle_block(next_sub['id']))           
        
        elif request.form['action'] == "left":

            prev_sub = query_db("SELECT * FROM line WHERE project_id = ? AND start <= ? AND id != ? ORDER BY start DESC LIMIT 1", (subtitle['project_id'], subtitle['start'], subtitle['id']), True)
            new_text = VTT.create_text(sanitize_line(text_right))
            text_left = prev_sub['text'] + " " + text_left
            text_left = VTT.create_text(sanitize_line(text_left))
            db.execute( "UPDATE line SET text = ?, end = ? WHERE id = ?", (text_left, time_at_cursor, prev_sub['id']))
            db.execute( "UPDATE line SET text = ?, start = ? WHERE id=?", (new_text, time_at_cursor, id))
            blocks.append(subtitle_block(prev_sub['id']))
            blocks.append(subtitle_block(id))

        db.commit()
        return make_response("\n".join(blocks), trigger= "subtitles_updated")
    return 500

@bp.route('/<int:id>/update_form', methods=('GET',))
def update_form(id):
    subtitle = get_subtitle_byId(id)
    if subtitle == None:
        if htmx:
            return "Subtitle not found", 404
        abort(404)
    return render_template('partials/subtitle_edit_inline.html', subtitle=subtitle)

# subtle filters

@bp.app_template_filter('vttline')
def vttline(text):
    return VTT.create_html(text)

@bp.app_template_filter('vtttime')
def vtttime(s) -> str:
    return VTT.create_time_label(float(s))

def sanitize_line(line:str):
    return ' '.join(line.split('\n'))

def subtitle_block(id:int):
    subtitle = get_subtitle_byId(id)
    if subtitle == None:
        return "Subtitle not found", 404
    return render_block('pages/editor.html', 'subtitle_block', subtitle=subtitle)

# reusable queries

def get_subtitle_byId(id):
    return query_db("SELECT * FROM line WHERE id = ?", (id,), True)