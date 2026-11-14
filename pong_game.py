"""Classic two-player Pong game with automatic OpenCV MP4 gameplay recording.

Player 1 controls the left paddle with W / S.
Player 2 controls the right paddle with Up / Down arrow keys.
Press ESC or close the window to quit and finalize the MP4 recording.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random
import sys

import cv2
import numpy as np
import pygame

# ---------------------------------------------------------------------------
# Configuration Constants
# ---------------------------------------------------------------------------

# Window & Timing
WINDOW_WIDTH: int = 960
WINDOW_HEIGHT: int = 600
WINDOW_TITLE: str = "Pong — 2P Classic (Auto-Recording)"
TARGET_FPS: int = 60
# Clamp frame delta time so dragging the OS window does not cause physics tunneling.
MAX_DELTA_TIME: float = 0.05
SERVE_DELAY_SECONDS: float = 0.55

# Colors (RGB for Pygame)
COLOR_BACKGROUND: tuple[int, int, int] = (16, 18, 24)
COLOR_FOREGROUND: tuple[int, int, int] = (240, 244, 248)
COLOR_DIVIDER: tuple[int, int, int] = (64, 72, 86)
COLOR_HUD_TEXT: tuple[int, int, int] = (168, 178, 194)
COLOR_P1_PADDLE: tuple[int, int, int] = (86, 180, 233)
COLOR_P2_PADDLE: tuple[int, int, int] = (230, 159, 0)
COLOR_BALL: tuple[int, int, int] = (255, 255, 255)
COLOR_REC_ACTIVE: tuple[int, int, int] = (235, 68, 56)
COLOR_REC_ERROR: tuple[int, int, int] = (245, 166, 35)

# Table, Typography, & HUD Layout
CENTER_LINE_WIDTH: int = 4
CENTER_DASH_HEIGHT: int = 18
CENTER_DASH_GAP: int = 14
SCORE_FONT_SIZE: int = 64
HUD_FONT_SIZE: int = 22
STATUS_FONT_SIZE: int = 20
SCORE_CENTER_Y: int = 52
HUD_BOTTOM_MARGIN: int = 16
REC_BADGE_X: int = 20
REC_BADGE_Y: int = 20
REC_DOT_RADIUS: int = 6
REC_TEXT_GAP: int = 10

# Paddle Settings
PADDLE_WIDTH: int = 14
PADDLE_HEIGHT: int = 96
PADDLE_MARGIN: int = 36
PADDLE_CORNER_RADIUS: int = 4
PADDLE_SPEED: float = 470.0  # pixels per second

# Ball Settings
BALL_SIZE: int = 16
BALL_INITIAL_SPEED: float = 410.0  # pixels per second
BALL_SPEED_INCREMENT: float = 28.0
BALL_MAX_SPEED: float = 860.0
MAX_BOUNCE_ANGLE_DEG: float = 50.0
INITIAL_SERVE_MIN_DEG: float = 12.0
INITIAL_SERVE_MAX_DEG: float = 32.0

# Controls
P1_UP_KEY: int = pygame.K_w
P1_DOWN_KEY: int = pygame.K_s
P2_UP_KEY: int = pygame.K_UP
P2_DOWN_KEY: int = pygame.K_DOWN
QUIT_KEY: int = pygame.K_ESCAPE

# Video Recording Settings
RECORDING_DIR: Path = Path("recordings")
RECORDING_FILENAME: str = "pong_game.mp4"
VIDEO_CODEC: str = "mp4v"


# ---------------------------------------------------------------------------
# Game Entities
# ---------------------------------------------------------------------------


@dataclass
class Paddle:
    """Represents a player-controlled paddle with sub-pixel vertical movement."""

    x: float
    y: float
    width: int
    height: int
    speed: float
    color: tuple[int, int, int]

    def __post_init__(self) -> None:
        self.rect = pygame.Rect(int(round(self.x)), int(round(self.y)), self.width, self.height)

    def move(self, direction: int, dt: float, bounds_height: int) -> None:
        """Move the paddle vertically and clamp it inside the playfield.

        Args:
            direction: -1 for up, +1 for down, 0 for stationary.
            dt: Elapsed time in seconds since the last frame.
            bounds_height: Height of the game window in pixels.
        """
        if direction == 0:
            return

        self.y += direction * self.speed * dt
        max_y = float(bounds_height - self.height)
        if self.y < 0.0:
            self.y = 0.0
        elif self.y > max_y:
            self.y = max_y

        self.rect.y = int(round(self.y))

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the paddle onto the target Pygame surface."""
        pygame.draw.rect(surface, self.color, self.rect, border_radius=PADDLE_CORNER_RADIUS)


@dataclass
class Ball:
    """Represents the Pong ball, including velocity, collisions, and serve reset."""

    size: int
    initial_speed: float
    speed_increment: float
    max_speed: float
    color: tuple[int, int, int]
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    speed: float = 0.0

    def __post_init__(self) -> None:
        self.rect = pygame.Rect(0, 0, self.size, self.size)

    def reset(self, bounds_width: int, bounds_height: int, serve_direction: int) -> None:
        """Center the ball and assign a fresh serve velocity.

        Args:
            bounds_width: Window width in pixels.
            bounds_height: Window height in pixels.
            serve_direction: +1 to serve right, -1 to serve left.
        """
        self.x = (bounds_width - self.size) / 2.0
        self.y = (bounds_height - self.size) / 2.0
        self.speed = self.initial_speed

        # Pick a non-flat launch angle so rallies start cleanly without stalling horizontally.
        angle_deg = random.uniform(INITIAL_SERVE_MIN_DEG, INITIAL_SERVE_MAX_DEG)
        angle_rad = math.radians(angle_deg) * random.choice((-1, 1))
        direction = 1 if serve_direction >= 0 else -1

        self.vx = direction * self.speed * math.cos(angle_rad)
        self.vy = self.speed * math.sin(angle_rad)
        self._sync_rect()

    def update(self, dt: float, bounds_height: int) -> None:
        """Advance ball position and handle top/bottom wall rebounds."""
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Reflect off the top or bottom wall and clamp position to prevent sticking.
        max_y = float(bounds_height - self.size)
        if self.y <= 0.0:
            self.y = 0.0
            self.vy = abs(self.vy)
        elif self.y >= max_y:
            self.y = max_y
            self.vy = -abs(self.vy)

        self._sync_rect()

    def bounce_off_paddle(self, paddle: Paddle, outgoing_x_dir: int) -> None:
        """Deflect the ball off a paddle based on where it struck the paddle face.

        Hitting near the paddle center returns a shallower shot; hitting near
        the top or bottom edge creates a sharper vertical angle and speeds up play.
        """
        paddle_center_y = paddle.y + paddle.height / 2.0
        ball_center_y = self.y + self.size / 2.0

        # Normalize impact offset to [-1.0, 1.0].
        relative_offset = (ball_center_y - paddle_center_y) / (paddle.height / 2.0)
        relative_offset = max(-1.0, min(1.0, relative_offset))

        bounce_angle = relative_offset * math.radians(MAX_BOUNCE_ANGLE_DEG)
        self.speed = min(self.speed + self.speed_increment, self.max_speed)

        self.vx = outgoing_x_dir * self.speed * math.cos(bounce_angle)
        self.vy = self.speed * math.sin(bounce_angle)

        # Snap outside the paddle rect so the ball cannot trigger a second collision next frame.
        if outgoing_x_dir > 0:
            self.x = float(paddle.rect.right)
        else:
            self.x = float(paddle.rect.left - self.size)
        self._sync_rect()

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the ball as a crisp circle centered inside its collision box."""
        center = (self.rect.centerx, self.rect.centery)
        pygame.draw.circle(surface, self.color, center, self.size // 2)

    def _sync_rect(self) -> None:
        self.rect.x = int(round(self.x))
        self.rect.y = int(round(self.y))


# ---------------------------------------------------------------------------
# OpenCV Video Recorder
# ---------------------------------------------------------------------------


def surface_to_bgr_frame(surface: pygame.Surface) -> np.ndarray:
    """Convert a Pygame display surface into an OpenCV-compatible BGR NumPy array.

    Pygame's ``surfarray.array3d`` returns a NumPy array with shape
    ``(width, height, 3)`` in RGB order. OpenCV's ``VideoWriter.write`` expects
    shape ``(height, width, 3)`` in BGR order with a C-contiguous uint8 buffer.
    """
    frame_whc_rgb = pygame.surfarray.array3d(surface)
    # Swap axes 0 (width) and 1 (height) to match OpenCV's (height, width, channels) layout.
    frame_hwc_rgb = np.transpose(frame_whc_rgb, (1, 0, 2))
    # Convert RGB -> BGR and guarantee a C-contiguous uint8 array for VideoWriter.
    frame_hwc_bgr = cv2.cvtColor(frame_hwc_rgb, cv2.COLOR_RGB2BGR)
    return np.ascontiguousarray(frame_hwc_bgr, dtype=np.uint8)


class VideoRecorder:
    """Records Pygame surface frames to an MP4 file using OpenCV."""

    def __init__(self, output_path: Path, width: int, height: int, fps: int, codec: str) -> None:
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.codec = codec
        self._writer: cv2.VideoWriter | None = None
        self.is_recording: bool = False
        self.error_message: str | None = None
        self.frames_written: int = 0

        self._initialize_writer()

    def _initialize_writer(self) -> None:
        """Create the output directory and open the OpenCV VideoWriter safely."""
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*self.codec)
            # Note: VideoWriter expects (width, height), opposite of NumPy's (height, width).
            writer = cv2.VideoWriter(
                str(self.output_path),
                fourcc,
                float(self.fps),
                (self.width, self.height),
            )
            if not writer.isOpened():
                writer.release()
                self.error_message = (
                    f"Could not open MP4 VideoWriter for {self.output_path} using codec '{self.codec}'."
                )
                print(f"[Recording Warning] {self.error_message}", file=sys.stderr)
                return

            self._writer = writer
            self.is_recording = True
            print(f"[Recording Started] Saving gameplay to {self.output_path}")
        except (OSError, cv2.error) as exc:
            self.error_message = f"Failed to initialize video recording: {exc}"
            print(f"[Recording Warning] {self.error_message}", file=sys.stderr)

    def write_surface(self, surface: pygame.Surface) -> None:
        """Capture and write a single rendered Pygame surface frame to the video file."""
        if not self.is_recording or self._writer is None:
            return

        try:
            frame_bgr = surface_to_bgr_frame(surface)
            self._writer.write(frame_bgr)
            self.frames_written += 1
        except (cv2.error, ValueError) as exc:
            self.error_message = f"Recording stopped due to frame write error: {exc}"
            print(f"[Recording Warning] {self.error_message}", file=sys.stderr)
            self.close()

    def close(self) -> None:
        """Release the VideoWriter and finalize the MP4 container."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            if self.frames_written > 0:
                print(
                    f"[Recording Saved] Wrote {self.frames_written} frames to {self.output_path}"
                )
        self.is_recording = False


# ---------------------------------------------------------------------------
# Rendering & Input Helpers
# ---------------------------------------------------------------------------


def read_paddle_inputs() -> tuple[int, int]:
    """Read current keyboard state and return (p1_direction, p2_direction)."""
    keys = pygame.key.get_pressed()

    p1_dir = int(keys[P1_DOWN_KEY]) - int(keys[P1_UP_KEY])
    p2_dir = int(keys[P2_DOWN_KEY]) - int(keys[P2_UP_KEY])
    return p1_dir, p2_dir


def draw_center_divider(surface: pygame.Surface) -> None:
    """Draw the classic dashed centerline down the middle of the court."""
    center_x = (WINDOW_WIDTH - CENTER_LINE_WIDTH) // 2
    y = 0
    while y < WINDOW_HEIGHT:
        dash_rect = pygame.Rect(center_x, y, CENTER_LINE_WIDTH, CENTER_DASH_HEIGHT)
        pygame.draw.rect(surface, COLOR_DIVIDER, dash_rect)
        y += CENTER_DASH_HEIGHT + CENTER_DASH_GAP


def draw_hud(
    surface: pygame.Surface,
    score_font: pygame.font.Font,
    hud_font: pygame.font.Font,
    status_font: pygame.font.Font,
    score_p1: int,
    score_p2: int,
    recorder: VideoRecorder,
) -> None:
    """Render scores, player controls, and live recording status onto the window."""
    # Scores placed symmetrically on each side of the centerline.
    p1_score_surf = score_font.render(str(score_p1), True, COLOR_P1_PADDLE)
    p2_score_surf = score_font.render(str(score_p2), True, COLOR_P2_PADDLE)

    p1_score_rect = p1_score_surf.get_rect(center=(WINDOW_WIDTH // 4, SCORE_CENTER_Y))
    p2_score_rect = p2_score_surf.get_rect(center=(3 * WINDOW_WIDTH // 4, SCORE_CENTER_Y))
    surface.blit(p1_score_surf, p1_score_rect)
    surface.blit(p2_score_surf, p2_score_rect)

    # On-screen controls / instructions.
    instructions = "P1: W / S    |    P2: Up / Down    |    ESC: Quit & Save MP4"
    instr_surf = hud_font.render(instructions, True, COLOR_HUD_TEXT)
    instr_rect = instr_surf.get_rect(
        centerx=WINDOW_WIDTH // 2,
        bottom=WINDOW_HEIGHT - HUD_BOTTOM_MARGIN,
    )
    surface.blit(instr_surf, instr_rect)

    # Recording status badge in the top-left corner.
    if recorder.is_recording:
        dot_center = (REC_BADGE_X + REC_DOT_RADIUS, REC_BADGE_Y + REC_DOT_RADIUS)
        pygame.draw.circle(surface, COLOR_REC_ACTIVE, dot_center, REC_DOT_RADIUS)
        status_text = f"REC  {recorder.output_path.as_posix()}"
        status_surf = status_font.render(status_text, True, COLOR_FOREGROUND)
        status_rect = status_surf.get_rect(
            left=dot_center[0] + REC_DOT_RADIUS + REC_TEXT_GAP,
            centery=dot_center[1],
        )
        surface.blit(status_surf, status_rect)
    else:
        status_text = "REC UNAVAILABLE (playing without video)"
        status_surf = status_font.render(status_text, True, COLOR_REC_ERROR)
        surface.blit(status_surf, (REC_BADGE_X, REC_BADGE_Y))


# ---------------------------------------------------------------------------
# Main Game Loop
# ---------------------------------------------------------------------------


def run_game() -> None:
    """Initialize Pygame and OpenCV, run the Pong loop, and clean up safely."""
    recorder: VideoRecorder | None = None

    try:
        pygame.init()
        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        clock = pygame.time.Clock()

        # Pygame's built-in default font requires no external font files.
        score_font = pygame.font.Font(None, SCORE_FONT_SIZE)
        hud_font = pygame.font.Font(None, HUD_FONT_SIZE)
        status_font = pygame.font.Font(None, STATUS_FONT_SIZE)

        output_path = RECORDING_DIR / RECORDING_FILENAME
        recorder = VideoRecorder(
            output_path=output_path,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            fps=TARGET_FPS,
            codec=VIDEO_CODEC,
        )

        paddle_start_y = (WINDOW_HEIGHT - PADDLE_HEIGHT) / 2.0
        left_paddle = Paddle(
            x=float(PADDLE_MARGIN),
            y=paddle_start_y,
            width=PADDLE_WIDTH,
            height=PADDLE_HEIGHT,
            speed=PADDLE_SPEED,
            color=COLOR_P1_PADDLE,
        )
        right_paddle = Paddle(
            x=float(WINDOW_WIDTH - PADDLE_MARGIN - PADDLE_WIDTH),
            y=paddle_start_y,
            width=PADDLE_WIDTH,
            height=PADDLE_HEIGHT,
            speed=PADDLE_SPEED,
            color=COLOR_P2_PADDLE,
        )

        ball = Ball(
            size=BALL_SIZE,
            initial_speed=BALL_INITIAL_SPEED,
            speed_increment=BALL_SPEED_INCREMENT,
            max_speed=BALL_MAX_SPEED,
            color=COLOR_BALL,
        )
        ball.reset(WINDOW_WIDTH, WINDOW_HEIGHT, serve_direction=random.choice((-1, 1)))

        score_p1 = 0
        score_p2 = 0
        serve_timer = SERVE_DELAY_SECONDS
        running = True

        while running:
            # 1. Compute clamped delta time in seconds.
            dt = min(clock.tick(TARGET_FPS) / 1000.0, MAX_DELTA_TIME)

            # 2. Process window and exit events.
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == QUIT_KEY:
                    running = False

            # 3. Update paddles (players can position paddles even during brief serve pauses).
            p1_dir, p2_dir = read_paddle_inputs()
            left_paddle.move(p1_dir, dt, WINDOW_HEIGHT)
            right_paddle.move(p2_dir, dt, WINDOW_HEIGHT)

            # 4. Update ball physics, paddle collisions, and scoring.
            if serve_timer > 0.0:
                serve_timer = max(0.0, serve_timer - dt)
            else:
                ball.update(dt, WINDOW_HEIGHT)

                if ball.vx < 0.0 and ball.rect.colliderect(left_paddle.rect):
                    ball.bounce_off_paddle(left_paddle, outgoing_x_dir=1)
                elif ball.vx > 0.0 and ball.rect.colliderect(right_paddle.rect):
                    ball.bounce_off_paddle(right_paddle, outgoing_x_dir=-1)

                # Check scoring boundaries (ball completely past left or right edge).
                # Serve toward the player who conceded the point.
                if ball.rect.right < 0:
                    score_p2 += 1
                    ball.reset(WINDOW_WIDTH, WINDOW_HEIGHT, serve_direction=-1)
                    serve_timer = SERVE_DELAY_SECONDS
                elif ball.rect.left > WINDOW_WIDTH:
                    score_p1 += 1
                    ball.reset(WINDOW_WIDTH, WINDOW_HEIGHT, serve_direction=1)
                    serve_timer = SERVE_DELAY_SECONDS

            # 5. Render the complete game frame to the display surface.
            screen.fill(COLOR_BACKGROUND)
            draw_center_divider(screen)
            left_paddle.draw(screen)
            right_paddle.draw(screen)
            ball.draw(screen)
            draw_hud(screen, score_font, hud_font, status_font, score_p1, score_p2, recorder)

            # Present the rendered frame and record the exact same surface pixels to MP4.
            pygame.display.flip()
            recorder.write_surface(screen)

    finally:
        if recorder is not None:
            recorder.close()
        pygame.quit()


if __name__ == "__main__":
    run_game()