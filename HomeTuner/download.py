import json
import logging
import youtube_dl
from flask import Flask, Blueprint, render_template, request, jsonify
from urllib.parse import unquote_plus
from googleapiclient.discovery import build
from HomeTuner.scan import get_mac_addresses
from config import SONGS, SONGS_DIR, DUMMY_MAC

logger = logging.getLogger(__name__)
# Flask
app = Flask(__name__)
downloader = Blueprint('downloader', __name__)


@downloader.route('/')
def home():
    with open(SONGS) as f:
        data = json.load(f)
    mac = get_guest_mac()
    return render_template('home.html', name=data['devices'][mac]['name'])


def get_guest_mac():
    try:
        mac = get_mac_addresses(hosts=request.remote_addr)[0]
    except IndexError:
        mac = DUMMY_MAC
    return mac


@downloader.route('/search')
def search():
    videos = youtube_search(request.args['k'])
    mac = get_guest_mac()
    with open(SONGS) as f:
        data = json.load(f)
        for vid in videos:
            try:
                vid['saved'] = vid['id'] in data['devices'][mac]['songs']
            except KeyError:
                vid['saved'] = False
    return jsonify({'mac': mac, 'videos': videos})


@downloader.route('/songs/<song_id>')
def get_song(song_id):
    pass


@downloader.route('/devices/<mac>/songs/', methods=['GET'])
def get_songs(mac):
    pass


@downloader.route('/devices/<mac>/songs/<song_id>', methods=['PUT'])
def put_song(mac, song_id):
    mac = unquote_plus(mac)
    logger.info("{} requesting to add {} to his songs".format(mac, song_id))
    ydl_opts = {'format': 'bestaudio/best',
                'outtmpl': '{}/%(id)s.%(ext)s'.format(SONGS_DIR),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'logger': logger,
                'progress_hooks': [manage_download]
                }
    with open(SONGS) as f:
        songs = json.load(f)
    songs['devices'][mac]['songs'][song_id] = 0  # initially sets song start time to 0
    download = True
    if song_id in songs['songs']:
        logger.info("Song already downloaded. Adding to user rotation..")
        songs['songs'][song_id]['savedBy'].append(mac)
        download = False
    else:
        songs['songs'][song_id] = {'progress': 0, 'savedBy': [mac]}
    with open(SONGS, 'w') as f:
        json.dump(songs, f)
    if download:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            url = "https://www.youtube.com/watch?v=" + song_id
            ydl.download([url])
    return jsonify(200)


@downloader.route('/devices/<mac>/songs/<song_id>', methods=['DELETE'])
def remove_song(mac, song_id):
    mac = unquote_plus(mac)
    pass


def manage_download(info):
    with open(SONGS) as f:
        songs = json.load(f)
    if info['status'] == 'error':
        logger.info("Error downloading: {}".format(info))
    else:
        filename = info['filename']
        id = filename[len(SONGS_DIR) + 1:filename.find('.')]
        try:
            songs['songs'][id]['progress'] = info['downloaded_bytes'] / info['total_bytes'] * 100
        except TypeError:  # total_bytes not available
            songs['songs'][id]['progress'] = 100 if info['status'] == 'finished' else 0
        logger.info("Download progress: {}%".format(songs['songs'][id]['progress']))
        with open(SONGS, 'w') as f:
            json.dump(songs, f)


def get_api_key():
    with open(".apikey") as f:
        return f.read()


def youtube_search(keyword):
    logger.info("Searching youtube videos with key={}".format(keyword))
    youtube = build('youtube', 'v3', developerKey=get_api_key(), cache_discovery=False)
    search_response = youtube.search().list(
        q=keyword,
        part='id,snippet',
        maxResults=6,
        type='video'
    ).execute()
    return [{'thumbnail': result['snippet']['thumbnails']['default']['url'],
             'id': result['id']['videoId'],
             'title': result['snippet']['title']} for result in search_response.get('items', [])]
