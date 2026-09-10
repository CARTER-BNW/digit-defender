"""Digit Defender entry point.

    python main.py [--seed N] [--frames N] [--fullscreen]

--frames N  auto-quits after N frames (scripted smoke runs / phase checks).
"""
import argparse
import sys

import pygame

from settings import WINDOW_W, WINDOW_H, WORLD_SEED
from game import Game


def parse_args(argv):
    p = argparse.ArgumentParser(description="Digit Defender")
    p.add_argument("--seed", type=int, default=WORLD_SEED)
    p.add_argument("--frames", type=int, default=None,
                   help="auto-quit after N frames")
    p.add_argument("--fullscreen", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pygame.init()
    flags = pygame.FULLSCREEN if args.fullscreen else 0
    size = (0, 0) if args.fullscreen else (WINDOW_W, WINDOW_H)
    screen = pygame.display.set_mode(size, flags)
    pygame.display.set_caption("Digit Defender")
    game = Game(screen, args.seed)
    game.run(max_frames=args.frames)
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
