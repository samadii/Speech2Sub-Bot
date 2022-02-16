import os, re, time
import shutil
import speech_recognition as sr
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from tqdm import tqdm
from segmentAudio import silenceRemoval
from writeToFile import write_to_file
from display_progress import progress_for_pyrogram

rec = sr.Recognizer()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
lang = os.environ.get("LANG_CODE")

Bot = Client(
    "Bot",
    bot_token = BOT_TOKEN,
    api_id = API_ID,
    api_hash = API_HASH
)

START_TXT = """
Hi {}
I am Speech2Sub Bot.

> `I can generate subtitles based on the speeches in medias.`

Send a video/audio/voice to get started.
"""

START_BTN = InlineKeyboardMarkup(
        [[
        InlineKeyboardButton('Source Code', url='https://github.com/samadii/Speech2Sub-Bot'),
        ]]
    )


@Bot.on_message(filters.command(["start"]))
async def start(bot, update):
    text = START_TXT.format(update.from_user.mention)
    reply_markup = START_BTN
    await update.reply_text(
        text=text,
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )


# Line count for SRT file
line_count = 0

def sort_alphanumeric(data):
    """Sort function to sort os.listdir() alphanumerically
    Helps to process audio files sequentially after splitting 
    Args:
        data : file name
    """
    
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)] 
    
    return sorted(data, key = alphanum_key)


def ds_process_audio(audio_file, file_handle):  
    # Perform inference on audio segment
    global line_count
    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = rec.record(source)
            text = rec.recognize_google(audio_data,language=lang)
            infered_text = text
    except:
        infered_text = ""
        pass
    
    # File name contains start and end times in seconds. Extract that
    limits = audio_file.split("/")[-1][:-4].split("_")[-1].split("-")
    
    if len(infered_text) != 0:
        line_count += 1
        write_to_file(file_handle, infered_text, line_count, limits)


@Bot.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.voice) & ~filters.edited, group=-1)
async def speech2srt(bot, m):
    global line_count
    if m.document and not m.document.mime_type.startswith("video/"):
        return
    media = m.audio or m.video or m.document or m.voice
    msg = await m.reply("`Downloading..`", parse_mode='md')
    audio_directory = "temp/"
    if not os.path.isdir(audio_directory):
        os.makedirs(audio_directory)
    c_time = time.time()
    file_dl_path = await bot.download_media(message=m, progress=progress_for_pyrogram, progress_args=("Downloading..", msg, c_time))
    await msg.edit("`Now Processing...`", parse_mode='md')
    audio_file_name = "temp/file.wav"
    os.system(f'ffmpeg -i "{file_dl_path}" -vn -y {audio_file_name}')

    print("Splitting on silent parts in audio file")
    silenceRemoval(audio_file_name)
    
    # Output SRT file
    srt_file_name = os.path.basename(file_dl_path).rsplit(".", 1)[0] + '.srt'
    file_handle = open(srt_file_name, "w")
    
    for file in tqdm(sort_alphanumeric(os.listdir(audio_directory))):
        audio_segment_path = os.path.join(audio_directory, file)
        if audio_segment_path.split("/")[-1] != audio_file_name.split("/")[-1]:
            ds_process_audio(audio_segment_path, file_handle)
            
    print("\nSRT file saved to", srt_file_name)
    file_handle.close()

    await m.reply_document(srt_file_name)
    await msg.delete()
    os.remove(file_dl_path)
    os.remove(srt_file_name)
    shutil.rmtree('temp/')
    line_count = 0


  
    
Bot.run()
