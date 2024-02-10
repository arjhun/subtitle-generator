import time
import io
from textwrap import wrap
import math

MAX_CHARS = 42

def create_text(text:str) -> str:
    text = "\n".join(wrap(text, MAX_CHARS))+"\n"
    return text

def create_html(text:str, element="<br>") -> str:
    text = element.join(text.split("\n"))
    return text

def from_file(filepath, lines):
    with open(filepath, 'w+') as subtitle_file:
        write_to_file(subtitle_file, lines)


def from_buffer(lines):
    output = io.BytesIO()
    write_to_file(output, lines, True)
    output.seek(0)
    return output
    
def write_to_file(file, lines, to_bytes=False):
        enc = 'utf-8'
        header = "WEBVTT\n\n"
        file.write(header if not to_bytes else bytes(header, enc))
        index = 1
        line: Line
        for line in lines:
            index_str = f"{str(index)}\n"
            time_label = f"{create_time_label(line.start_time)} --> {create_time_label(line.end_time)}\n"
            text = f"{create_text(line.text)}\n\n"
            file.write(index_str if not to_bytes else bytes(index_str, enc))
            file.write(time_label if not to_bytes else bytes(time_label, enc))
            file.write(text if not to_bytes else bytes(text, enc))
            index+=1

def create_time_label(seconds:float) -> str :
            (ms, s) = math.modf(seconds)
            return ".".join([time.strftime('%H:%M:%S', time.gmtime(s)), str(round(ms*1000)).zfill(3)])

class Line:
    start_time:float
    end_time:float
    text:str

    def __init__(self, text:str, start_time:float, end_time:float):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time