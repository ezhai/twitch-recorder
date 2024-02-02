# Stream Recorder for Twitch

A simple 24/7 script to record streams from Twitch.

This fork is based on the following projects.
- [twitch-stream-recorder](https://github.com/ancalentari/twitch-stream-recorder)
-  [twitch-recorder](https://gist.github.com/junian/b41dd8e544bf0e3980c971b0d015f5f6)


## Additional Features
- Automatically add metadata tags (i.e. stream title, broadcast date) to the recorded video file.
- Adds chapters to the recorded video files based on game category.

## Usage

```
python twitch-recorder.py -u <username>
```

## Installation

- [Python 3.11+](https://www.python.org/downloads/)
- [Streamlink](https://github.com/ancalentari/twitch-stream-recorder)
- [FFmpeg](https://ffmpeg.org/download.html) (needed for streamlink)

*Tip: If your operating system uses a package manager, use that to install the prerequisites.*


Confirm that the executables are installed. If the your executable is named differently or is not on your PATH, use that name instead (e.g. `C:\\bin\ffmpeg.exe`).
```
python --version
streamlink --version
ffmpeg -version
ffprobe -version
```

You will also need to install the `requests` Python module.
```
python -m pip install -r requirements.txt
```
*Tip: Use your operating system's package manager or a Python virtual environment to install Python modules.*

## Configuration

Rename/copy `config.py.template` to `config.py`. Edit the configuration variables in `config.py`.

### Twitch API Credentials (required)
Login to the [Twitch Developer Console](https://dev.twitch.tv/console/apps) and register an application. After your application is created, you can retrieve the Client ID and Secret from the app page.

### Twitch OAuth Token (optional)
By default, ad segments will be filtered out of the recorded video leaving a discontinuity in your video. Your Twitch OAuth Token can be used with Streamlink to avoid having these discontinuities by completely bypass ads if you are subscribed to the channel you are recording or have Twitch Turbo. Login to [twitch.tv](https://twitch.tv/), open the browser console using *F12* or *Ctrl+Shift+I* and paste the following command into the console. This is the token used by Twitch servers to authenticate your Twitch account, so be careful with it.
```
document.cookie.split("; ").find(item=>item.startsWith("auth-token="))?.split("=")[1]
```

*Note: Generally, you should avoid pasting random commands you find on the internet into your browser console, but this one won't do anything bad. :P*

## Contribution

Have any issues or suggestions to improve the code? Feel free to open an issue or a pull request!
