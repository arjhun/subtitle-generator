# Subtitle generator

A 'simple' subtitle generator created for my final project for CS50 2024 using google cloud speech-to-text api, flask, HTMX and Celery with RabbitMQ.
CAUTION: this project is purely a prototype. Use at your own discretion! Because of the scope of the final project I decided not to implement authentication!
the flask project can be deployed in a WSGI server for production. But as a self hosted tool on a private network it runs fine for now.
This project uses a paid API that has a free tier, please consult the GCLOUD documentation on quotas and billing.

### Video Demo CS50 3 minute version:  [youtube](https://youtu.be/0nl3Gq8Ol1w)

## Table of Contents

- [Subtitle generator](#subtitle-generator)
    - [Video Demo CS50 3 minute version:  youtube](#video-demo-cs50-3-minute-version--youtube)
  - [Table of Contents](#table-of-contents)
  - [Installation for development](#installation-for-development)
  - [Project explained](#project-explained)
  - [Out of scope improvements](#out-of-scope-improvements)
  - [Acknowledgements](#acknowledgements)
  - [Support](#support)
  - [Contributing](#contributing)
  


## Installation for development
(assuming you are running this in linux or WSL)

1. Make sure you create a project and setup billing in google cloud
2. Make sure you can [authenticate](https://cloud.google.com/docs/authentication) through a service account json file (not recommended) or better use gcloud CLI to setup Application Default Credentials 
3. Clone this repository
4. Install ffmpeg and make sure the `ffmpeg` and `ffprobe` commands are on your PATH 
   ```
   bash sudo apt-get install ffmpeg
   ```
5. Make sure you run RabbitMQ running it through a docker container is surprisingly easy!
   
   ```
   docker run -d -p 5672:5672 rabbitMQ
   ```
6. create and enter virtual environment in your repo folder
   
   ```
   python -m venv .venv
   source .venv/bin/activate
   ```
7. install all dependencies
   
   ``` 
   pip install -r requirements.txt
   ```
8. Run the Celery worker, this is going to accept all the tasks from our app. With this command it runs in the foreground, you probably want to daemonize this file in production.
   
   ```
   celery -A subtitler.celery_worker  worker --loglevel INFO
   ```
9.  Init the database
    ```
    flask --app subtitler init-db
    ```
10. Make sure you configure your application through the config. [You can overwrite](https://flask.palletsprojects.com/en/2.3.x/config/#instance-folders) the app.config in a `config.py` file in a folder called `instance` in the root folder of the cloned repo. if you start the application the folder will be created automatically, these are the most important config keys:
    
    example config.py:
    ```python
       # please use a random and private key for production don't commit this key into a VCS 
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
    ```
11. Run the subtitler flask app in debug mode
    ```
    flask --app subtitler/ run --debug
    ```
12.  Go to http://localhost:5000 and start creating subtitles!

## Project explained

- `subtitler/__init__.py`
  
  This file turns the subtitler application into a regular package. I choose the application factory with blueprints strategy to make sure the multiple applications can be instantiated and each route lives in it's own file. This also makes deploying the application and future testing of the application easier. In the root `__init__.py` file all the extensions are registered with the app, these will get their config from the application context when the config object is created for later use throughout the application. This application can later be used in your Celery worker.
- `subtitler/static/`
  
  The static folder will contain all the static files for the frontend like CSS, javascript, images, favicons and other static files. 
- `subtitler/tasks/video.py`
  
  The tasks folder contains all the Celery long running tasks. In this case it will contain one task ```video.process()``` in the package `video.py`. This task will do all the work when the video is received, using the util package `speech_interface.py`. This function will communicate with the celery worker and handle resubmission and result processing. At the moment I am not keeping track of results. But the tasks will update the database and I use the project.status column to check the status of the processing by means of polling.

- `subtitler/utils/speech_interface.py`
  
  This is the utility package that takes care of all the processing of the video, in short it contains functions that:

    1. will use FFPROBE to check for a valid video.
    2. will extract a poster image from the video using FFMPEG
    3. will extract the audio to a *.flac file through FFMPEG
    4. will upload this *.flac to a gcloud storage bucket
    5. will start transcribing this *.flac file to transcribe the speech to a LongRunningRecognizeResponse object
    6. will process these results and take all the offsets from wordinfo objects and cut all the transcripts up into two line 42 character wide subtitle lines.
    7. will store these lines in the database under the project id with text, start and end times for later use.
- `subtitler/utils/VTT.py`

  This package contains functions that create a VTT file from our database entries. But also contain functions that transform floats to proper VTT time labels.
  For example: `create_time_label(140.123)` will output `00:02:20.123` conform VTT standard.

  It also contains functions to load a VTT file as a StringIO in-memory file-like object for creating a *.VTT file on the fly. 

- `subtitler/celery_worker.py`

  This is the file that gets run by Celery, when running it contains an entire instance of our application allowing you to interact with the database and other functions. 
- `subtitler/celery.py`

  This file is used to init Celery.
- `subtitler/db.py`
  
  This file creates, registers and initializes our database. It also registers some `Click` command-line functions and also contains some functions for retrieving rows from the database. 
- `subtitler/htmx.py`
  
  Together with the HTMX javascript file. I'm using the flask-htmx package to simplify generating htmx specific responses and process htmx specific requests. HTMX is build on the HATEOAS (hypermedia as the state of application state) concept. Instead of sending large json objects and a large client library that has to maintain a representation of the state of the application client side. HTMX will retrieve the state server side by replacing html in the dom by retrieving html components rendered server-side. 
- `subtitler/templates`

  This folder contains all the Jinja templates. A base layout, pages, partials and other includes. Jinja works really well together with htmx, and the jinja2-fragments package that makes rendering a inline block from your template possible when a request comes from htmx and keeps all your blocks in the same file as the entire page. example:
  ```python
  if htmx:
    # this is a htmx request render only the project table
    return render_block('pages/projects.html', 'projects_block', projects = projects, pagination = pagination)
  # it is a normal request from the browser send back the entire project page
  return render_template('pages/projects.html', projects = projects, pagination = pagination)
  ```     
- `subtitler/subtitles.py`
  
  This is the blueprint for all the subtitle routes. It contains all the endpoints for dealing with subtitle lines. It also contains al the functions that modify subtitles and filters for our templates.
- `subtitler/projects.py`
  
  This is the blueprint for all the project routes. It contains all the endpoints for dealing with your project. It also contains al the functions that modify your project and the function that starts a task in a celery worker.
- `requirements.txt`
  
  The requirements file tells pip to install all the right packages in your venv folder (when activated)!

## Out of scope improvements

- Proper error handling everywhere
- Authentication
- VTT parsing for generating editable subtitles from a VTT file.
- During the development of this app it became apparent to me how well all the GCloud APIs work together. While I really like self hosting everything. Creating and managing tasks running a message queue and implementing authentication between services and users is a lot of overhead. This project will benefit a lot from moving it entirely to the cloud with app engine, cloud functions, cloud triggers cloud storage and database all in the google ecosystem.
- It currently uses API v1 but should switch to API v2 soon to benefit from nice features like: batched long running tasks and higher quality transcriptions. These are also cheaper.
- move to SCSS, Tailwind or move towards using a pre built frontend library. I created all the CSS and components myself, but does not feel very scalable at the moment, but I like doing it.

## Acknowledgements

  Thanks to all the maintainers for these packages. You can read more about the technologies used below:
- [Cloud speech-to-text API](https://cloud.google.com/speech-to-text/docs/transcribe-api)
- [Flask](https://flask.palletsprojects.com/en/3.0.x/)
- [flask-htmx](https://github.com/edmondchuc/flask-htmx)
- [jinja2-fragments](https://github.com/sponsfreixes/jinja2-fragments)
- [ffmpeg-python](https://github.com/kkroening/ffmpeg-python)
- [HTMX](https://htmx.org/)
- [Celery + RabbitMQ](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#choosing-a-broker)

check out CS50: https://cs50.harvard.edu/x/2024/

## Support

Please [open an issue](https://github.com/arjhun/subtitle-generator/issues/new) for support.

## Contributing

Please contribute using [Github Flow](https://guides.github.com/introduction/flow/). Create a branch, add commits, and [open a pull request](https://github.com/arjhun/subtitle-generator/compare/).
