import os

from flask import Flask, render_template
from . import celery

def create_app(test_config=None) -> Flask:
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # please use a random and private key don't commit this key into a VCS 
        SECRET_KEY = "dev",
        # configure these paths in your instance folder config.py for file uploads in a containerized read-only env
        DATABASE = os.path.join(app.instance_path, 'subtitler.sqlite'),
        UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads'),
        # change this to your created storage bucket for your gcloud storage bucket
        STORAGE_BUCKET = 'your_gc_bucket',
        ALLOWED_EXTENSIONS = {'m4v','mp4','h264','mov'},
        MAX_CONTENT_LENGTH = 32 * 1000 * 1000,
        PAGE_SIZE = 5,
        CELERY=dict(
            broker_url= "pyamqp://guest@localhost",
            result_backend = "rpc://",
            task_ignore_Result = True
        )
    )
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

        # app name 
    @app.errorhandler(404) 
    def not_found(e):
        return render_template("pages/404.html"), 404
    
    celery.celery_init_app(app)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    from . import db
    db.init_app(app)

    from .htmx import htmx
    htmx.init_app(app)

    from . import projects
    app.register_blueprint(projects.bp)
    app.add_url_rule('/', endpoint='index')

    from . import subtitles
    app.register_blueprint(subtitles.bp)
    
    return app