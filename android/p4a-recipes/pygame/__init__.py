"""pygame-ce for python-for-android.

The stock p4a `pygame` recipe builds pygame 2.1.0 (2021), whose Cython
modules do not compile against the Python 3.14 that p4a ships now
(`longintrepr.h` is gone). This local recipe (buildozer `p4a.local_recipes`)
keeps the stock build steps but points them at pygame-ce, the pygame the
desktop game runs on, so the phone gets the same API. pygame-ce ships the
same `buildconfig/Setup.Android.SDL2.in` template with the same placeholders.

Two adjustments to the stock steps:
- pygame-ce cythonizes src_c/cython/**/*.pyx from setup.py, so Cython must be
  importable by p4a's host python (`hostpython_prerequisites`).
- pygame-ce's pyproject.toml names meson-python as build backend; p4a's install
  step (`pip install .`) would then run a native meson build that cannot
  execute the cross-compiled sanity check. The pyproject is rewritten to the
  setuptools legacy backend, which runs the very setup.py p4a compiled with,
  and pip is told not to isolate the build (host setuptools + Cython are
  already there).
"""
from os.path import join

from pythonforandroid.logger import info, shprint
from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory

SETUPTOOLS_BACKEND = '''[build-system]
requires = ["setuptools>=64", "cython>=3.0.11"]
build-backend = "setuptools.build_meta:__legacy__"

'''


def _drop_table(lines, header):
    """Remove a TOML table (its header line up to the next header)."""
    out, skipping = [], False
    for line in lines:
        if line.strip() == header:
            skipping = True
            continue
        if skipping and line.startswith("["):
            skipping = False
        if not skipping:
            out.append(line)
    return out


class PygameCERecipe(CompiledComponentsPythonRecipe):
    version = '2.5.8'
    url = 'https://github.com/pygame-community/pygame-ce/archive/refs/tags/{version}.tar.gz'

    site_packages_name = 'pygame'
    name = 'pygame'

    depends = ['sdl2', 'sdl2_image', 'sdl2_mixer', 'sdl2_ttf', 'setuptools', 'jpeg', 'png']
    call_hostpython_via_targetpython = False  # setuptools runs on the host python
    install_in_hostpython = False
    hostpython_prerequisites = ['setuptools', 'Cython>=3.0.11']

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup_template = open(join("buildconfig", "Setup.Android.SDL2.in")).read()
            env = self.get_recipe_env(arch)
            env['ANDROID_ROOT'] = join(self.ctx.ndk.sysroot, 'usr')

            png = self.get_recipe('png', self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), '.libs')
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe('jpeg', self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            sdl_mixer_includes = ""
            sdl2_mixer_recipe = self.get_recipe('sdl2_mixer', self.ctx)
            for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                sdl_mixer_includes += f"-I{include_dir} "

            sdl2_image_includes = ""
            sdl2_image_recipe = self.get_recipe('sdl2_image', self.ctx)
            for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                sdl2_image_includes += f"-I{include_dir} "

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I" + join(self.ctx.bootstrap.build_dir, 'jni', 'SDL', 'include') +
                    " -L" + join(self.ctx.bootstrap.build_dir, "libs", str(arch)) +
                    " -L" + png_lib_dir + " -L" + jpeg_lib_dir + " -L" + arch.ndk_lib_dir_versioned),
                sdl_ttf_includes="-I" + join(self.ctx.bootstrap.build_dir, 'jni', 'SDL2_ttf'),
                sdl_image_includes=sdl2_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes=""
            )
            open("Setup", "w").write(setup_file)
            self._use_setuptools_backend()

    @staticmethod
    def _use_setuptools_backend():
        """Swap pyproject.toml's meson-python build backend for setuptools'
        legacy one (idempotent)."""
        with open("pyproject.toml") as fh:
            text = fh.read()
        if "mesonpy" not in text:
            return
        lines = text.splitlines(keepends=True)
        lines = _drop_table(lines, "[build-system]")
        lines = _drop_table(lines, "[tool.meson-python.args]")
        with open("pyproject.toml", "w") as fh:
            fh.write("".join(lines).rstrip("\n") + "\n\n" + SETUPTOOLS_BACKEND)
        info("pygame-ce: pyproject.toml build backend switched to setuptools (legacy) for the p4a install step")

    def install_python_package(self, arch, name=None, env=None, is_dir=True):
        if env is None:
            env = self.get_recipe_env(arch)
        info('Installing pygame-ce into site-packages (setuptools backend, no build isolation)')
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(self._host_recipe.pip, 'install', '.', '--no-build-isolation', '--no-deps',
                    '--compile', '--target', self.ctx.get_python_install_dir(arch.arch), _env=env)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env['USE_SDL2'] = '1'
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env


recipe = PygameCERecipe()
