"""Digit Defender entry point.

    python main.py [--world NAME [--seed N]] [--frames N] [--fullscreen] [--autosave S]

--world NAME   skip the menu: resume that world (create it if missing)
--frames N     auto-quit after N frames (scripted smoke runs / phase checks)
--autosave S   override the autosave interval in seconds (tests)
"""
import argparse
import sys

import pygame

from settings import WINDOW_W, WINDOW_H, WORLD_SEED
from world import persistence
from world import testworld
from render import numbers
from ui import prefs
from ui.menu import Menu
from game import Game


def parse_args(argv):
    p = argparse.ArgumentParser(description="Digit Defender")
    p.add_argument("--world", default=None, help="play this world directly (created if missing)")
    p.add_argument("--seed", type=int, default=None, help="seed for a new --world")
    p.add_argument("--frames", type=int, default=None, help="auto-quit after N frames")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--autosave", type=float, default=None, help="autosave interval (s)")
    p.add_argument("--testworld", action="store_true",
                   help="open the Test Lab world (every part and junction type laid out around the HQ)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pygame.init()
    numbers.reset()          # fonts cached before a previous pygame.quit() are dead
    config = persistence.load_config()
    prefs.apply(config)                              # text / button scale (menu Settings)
    fullscreen = args.fullscreen or config.get("fullscreen", False)
    screen = pygame.display.set_mode((0, 0) if fullscreen else (WINDOW_W, WINDOW_H),
                                     pygame.FULLSCREEN if fullscreen else 0)
    pygame.display.set_caption("Digit Defender")

    while True:
        lab = args.testworld
        if args.testworld:
            meta = persistence.find_or_create(testworld.NAME, testworld.SEED)
        elif args.world:
            meta = persistence.find_or_create(args.world, args.seed)
        else:
            choice = Menu(config, max_frames=args.frames).run()
            if choice["action"] == "quit":
                break
            meta = choice["meta"]
            lab = choice.get("lab", False)
        game = Game.load(pygame.display.get_surface(), meta)
        game.apply_config(config)                 # hints panel, wave pause
        if lab:
            if testworld.is_empty(game.factory):
                testworld.build(game.factory)
            else:
                testworld.top_up(game.factory)        # parts added to the legend since this lab was built
        if args.autosave is not None:
            game.autosave_s = args.autosave
        result = game.run(max_frames=args.frames)
        config["last_world"] = meta["slug"]
        config["fullscreen"] = game.fullscreen
        config["minimap"] = not game.hud.minimap_hidden
        persistence.save_config(config)
        if result == "reload":
            continue                                  # Game.load re-reads the last save
        if result == "quit" or args.world or args.testworld:
            break

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
