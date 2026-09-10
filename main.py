"""Digit Defender entry point.

    python main.py [--seed N] [--frames N] [--fullscreen]

--frames N  auto-quits after N frames (scripted smoke runs / phase checks).
"""
import argparse
import sys

import pygame

from settings import WINDOW_W, WINDOW_H, FPS, WORLD_SEED, COLORS


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
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), flags)
    pygame.display.set_caption("Digit Defender")
    clock = pygame.time.Clock()

    frames = 0
    running = True
    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
        screen.fill(COLORS["bg"])
        pygame.display.flip()
        frames += 1
        if args.frames is not None and frames >= args.frames:
            running = False

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
