from celery import shared_task
from celery.utils.log import get_task_logger
from subtitler.db import get_db
from flask import current_app
import os
from subtitler.modules import speech_interface as speech
logger = get_task_logger(__name__)
# if you want to do something with the results use ignore_result=False as a function argument
# because we are ignoring everything by default
@shared_task()
def process(project_id, filepath):
    with current_app.app_context():
        db = get_db()
        try:
            bucket = current_app.config['STORAGE_BUCKET']
            set_status( "extracting", project_id)
            logger.info("Extracting audio")
            outfile = speech.process_video_and_audio(filepath)
            logger.info("Done extracting")
            logger.info(f"Sending audio file:{outfile} to bucket: {bucket}")
            filename = os.path.basename(outfile)
            speech.send_to_bucket(bucket, outfile, filename)
            logger.info("Transcribing speech")
            set_status( "transcribing", project_id )
            results = speech.transcribe_model_selection(speech_file=f"gs://{bucket}/{filename}", sample_rate = 44100)
            set_status( "processing", project_id )
            lines = speech.process_results(results)
            logger.info(f"Done transcribing audio to {len(lines)} lines")
            
            new_lines = []
            
            for line in lines:
                new_line = (project_id, line.start_time, line.end_time, line.text)
                new_lines.append(new_line)
            
            db.executemany("INSERT INTO line (project_id, start, end, text) VALUES (?, ?, ?, ?)", new_lines)
            db.commit()
            set_status("done", project_id)
        except Exception as err:
            logger.error(f"Unexpected {err=}, {type(err)=}")
            set_status("error", project_id)
            raise
            
    return "OK"

def set_status(status:str, project_id:int):
    db = get_db()
    db.execute("UPDATE project SET status = ? WHERE id = ?", (status,project_id,))
    db.commit()