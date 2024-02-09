from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from tqdm import tqdm
from segmentAudio import silenceRemoval
from writeToFile import write_to_file
from display_progress import progress_for_pyrogram
import requests
import wave, math, os, json, shutil, subprocess, asyncio, time, re
from vosk import Model, KaldiRecognizer


BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
# vosk supported language(code), see supported languages here: https://github.com/alphacep/vosk-api
LANGUAGE_CODE = os.environ.get("LANG_CODE", "en-us")
# language model download link (see available models here: https://alphacephei.com/vosk/models)
MODEL_URL = os.environ.get("MODEL_DOWNLOAD_URL", "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip")


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

def download_and_unpack_models(model_url):
    print("Start Downloading the Language Model...")
    r = requests.get(model_url, allow_redirects=True)

    total_size_in_bytes = int(r.headers.get('content-length', 0))
    block_size = 1024  # 1 Kibibyte
    progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)

    file_name = model_url.split('/models/')[1]
    with open(file_name, 'wb') as file:
        for data in r.iter_content(block_size):
            progress_bar.update(len(data))
            file.write(data)
    progress_bar.close()

    if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
        print("ERROR, something went wrong")
    else:
        print("Downloaded Successfully. Now unpacking the model..")
        shutil.unpack_archive(file_name)
        model_target_dir = f'model-{LANGUAGE_CODE}'
        if os.path.exists(model_target_dir):
            os.remove(model_target_dir)
        os.rename(file_name.rsplit('.', 1)[0], model_target_dir)
        print("unpacking Done.")

    os.remove(file_name)

if not os.path.exists(f'model-{LANGUAGE_CODE}'):
    download_and_unpack_models(MODEL_URL)

# Initialize model
model = Model(f'model-{LANGUAGE_CODE}')
sample_rate = 16000
rec = KaldiRecognizer(model, sample_rate)

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
    global line_count
    # File name contains start and end times in seconds. Extract that
    limits = audio_file.split("/")[-1][:-4].split("_")[-1].split("-")
    subprocess.call(['ffmpeg', '-loglevel', 'quiet', '-i',
                     'temp/file.wav', '-ss', limits[0], '-to', limits[1],
                     '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', '-y',
                     'temp/mono.wav'])

    wf = wave.open('temp/mono.wav', "rb")
    data = wf.readframes(wf.getnframes())
    if rec.AcceptWaveform(data):
        result_dict = json.loads(rec.Result())
        infered_text = result_dict.get("text", "")
    else:
        infered_text = ""

    if len(infered_text) != 0:
        line_count += 1
        write_to_file(file_handle, infered_text, line_count, limits)


@Bot.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.voice) & ~filters.edited, group=-1)
async def speech2srt(bot, m):
    global line_count
    if m.document and not m.document.mime_type.startswith("video/"):
        return
    media = m.audio or m.video or m.document or m.voice
    msg = await m.reply("`Downloading..`")
    audio_directory = "temp/"
    if not os.path.isdir(audio_directory):
        os.makedirs(audio_directory)
    c_time = time.time()
    file_dl_path = await bot.download_media(message=m, progress=progress_for_pyrogram, progress_args=("Downloading..", msg, c_time))
    await msg.edit_text("`Now Processing...`")
    audio_file_name = "temp/file.wav"
    os.system(f'ffmpeg -i "{file_dl_path}" -vn -y {audio_file_name}')

    print("Splitting on silent parts in audio file")
    silenceRemoval(audio_file_name)
    
    # Output SRT file
    srt_file_name = os.path.basename(file_dl_path).rsplit(".", 1)[0] + '.srt'
    file_handle = open(srt_file_name, "w")
    
    for file in tqdm(sort_alphanumeric(os.listdir(audio_directory))):
        audio_segment_path = os.path.join(audio_directory, file)
        if not audio_segment_path.split("/")[-1] in [audio_file_name.split("/")[-1], 'mono.wav']:
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
