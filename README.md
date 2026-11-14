# Pong with Automatic OpenCV MP4 Recording

A local two-player Pong game built with **Pygame** that automatically records every rendered frame to an MP4 video file using **OpenCV** (`cv2`) and **NumPy**, with no external image, font, or audio assets.

## Requirements

- **Python 3.10 or newer**
- Dependencies listed in `requirements.txt`:
  - `pygame`
  - `opencv-python`
  - `numpy`

## Setup & Installation

1. Create and activate a virtual environment (recommended):

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install the required packages:

   ```bash
   pip install -r requirements.txt
   ```

## Running the Game

```bash
python pong_game.py
```

*(On systems where `python` points to Python 2 or is unset, run `python3 pong_game.py`.)*

## Controls

| Action | Key |
| --- | --- |
| Player 1 (Left Paddle) Up / Down | `W` / `S` |
| Player 2 (Right Paddle) Up / Down | `Up Arrow` / `Down Arrow` |
| Quit & Finalize Recording | `ESC` or close window |

## Gameplay Recording

The latest gameplay recording is saved at `recordings/pong_game.mp4`.

<video src="recordings/pong_game.mp4" controls width="640">
  Your Markdown viewer does not support embedded video. [Open the recording](recordings/pong_game.mp4).
</video>

## Recording Behavior & Output Location

- **Output file:** `recordings/pong_game.mp4`
- **Automatic directory creation:** The `recordings/` directory is created automatically if it does not already exist.
- **Automatic start & stop:** Recording begins as soon as the game window opens and captures the entire rendered window (`960x600` at `60` FPS), including scores, paddles, ball, on-screen controls, and the live `REC` indicator.
- **Overwriting:** Each new session overwrites `recordings/pong_game.mp4`. Rename or copy the file after exiting if you want to keep multiple recordings.
- **Graceful fallback:** If OpenCV cannot open the MP4 `VideoWriter`, a warning is printed to `stderr`, the in-game status updates to `REC UNAVAILABLE (playing without video)`, and the game continues running normally without crashing.
- **Clean shutdown:** Always exit cleanly via `ESC` or the window close button (rather than forcefully killing the process) so OpenCV releases the writer and finalizes the MP4 file header properly.

## Codec & Platform Caveats

- **Codec (`mp4v`):** The script uses OpenCV's `mp4v` FourCC codec for broad out-of-the-box compatibility across Windows, macOS, and Linux wheels of `opencv-python`.
  - Some older web browsers or strict media players prefer H.264 (`avc1`) over `mp4v`. If your player will not open `pong_game.mp4`, play it in VLC/mpv/QuickTime or re-encode with FFmpeg (`ffmpeg -i recordings/pong_game.mp4 -c:v libx264 out.mp4`), or change `VIDEO_CODEC` in `pong_game.py` if your OpenCV build supports another codec.
- **Linux / Wayland & Headless Environments:** Pygame requires an active desktop display (`X11` or `Wayland`). On minimal Linux distributions, you may need system SDL/video codec libraries installed if `pygame` or `cv2.VideoWriter` fails to initialize.
- **Frame Timing:** Playback speed assumes the game runs near the `60` FPS target (`TARGET_FPS`). If your machine runs significantly slower than 60 FPS during a session, the saved video will play back slightly faster than real time because OpenCV writes one frame per rendered tick at a fixed 60 FPS container rate.