import math
import os
import threading
from typing import List, Callable

import imageio as imageio
import numpy as np
from PIL import UnidentifiedImageError
from natsort import natsorted

from .ingredient import Ingredient
from .pierogi import Pierogi
from .recipe import Recipe


class Dish(Ingredient):
    """
    crop and cook an entire recipe for all pixels

    create a Dish from:
    - single Pierogi
    - list of Pierogis
    - image file
    - video file
    - directory
    """

    _pierogis: List[Pierogi] = None
    _frames: int = None
    _fps: int = None

    @property
    def frames(self):
        if self._frames is None:
            self._frames = len(self.pierogis)
        return self._frames

    @property
    def frames(self):
        if self._frames is None:
            self._frames = len(self.pierogis)
        return self._frames

    def prep(
            self,
            pierogis: List[Pierogi] = None,
            loader: Callable[[], List[Pierogi]] = None,
            recipe=None,
            fps: float = None,
            **kwargs
    ):
        """
        set the recipe to cook for this dish

        :param recipe: something callable that returns a
        cook(pixels) method.
        Any Ingredient (including recipe) is an example of this

        :param pierogis: a list of Pierogi to cook
        """

        if pierogis is not None:
            loader = lambda: pierogis

        self._loader = loader
        self.fps = fps

        if recipe is None:
            recipe = Recipe()
        self.recipe = recipe

    @property
    def pierogis(self) -> List[Pierogi]:
        if self._pierogis is None:
            self.load()

        return self._pierogis

    def load(self) -> None:
        """
        use the loader return the contained pixels one time
        """
        self._pierogis = self._loader()

    @classmethod
    def _file_loader(cls, file: str) -> List[Pierogi]:
        reader = imageio.get_reader(file)
        frames = reader.get_length()

        # first try to load as video/animation
        if math.isinf(frames):
            pierogis = []

            for pierogi in cls._stream_loader(reader, lazy=True):
                pierogis.append(pierogi)

        else:
            pierogis = []

            for frame_index in range(frames):
                pierogis.append(
                    Pierogi.from_path(file, frame_index)
                )

        return pierogis

    @classmethod
    def _stream_loader(cls, stream, lazy: bool = True):
        if lazy:
            for frame_index in range(stream.count_frames()):
                path = stream.request.filename
                pierogi = Pierogi.from_path(path=path, frame_index=frame_index)
                yield pierogi

        else:
            for frame in stream:
                def loader():
                    return np.rot90(np.asarray(frame), axis=(1, 0))

                pierogi = Pierogi(loader=loader)
                yield pierogi

    @classmethod
    def _dir_loader(cls, dir: str, order_name: str = None) -> List[Pierogi]:
        pierogis = []

        if order_name is None:
            files = natsorted(os.listdir(dir))

        else:
            files = natsorted([filename for filename in os.listdir(dir) if filename.startswith(order_name)])

        for file in files:
            file_path = os.path.join(dir, file)

            if not os.path.isfile(file_path):
                continue

            # files are loaded just to check if valid and this thread is probably blocking
            def target():
                pierogi = cls._file_loader(file_path)[0]
                pierogi.load()
                pierogis.append(pierogi)

            try:
                thread = threading.Thread(target=target)
                thread.run()

            except UnidentifiedImageError:
                # print("{} is not an image".format(file))
                continue

            except ValueError:
                # print("{} is not an image".format(file))
                continue

            except IsADirectoryError:
                # print("{} is a directory".format(file))
                continue

        return pierogis

    @classmethod
    def from_path(cls, path: str, order_name: str = None) -> 'Dish':
        fps = None
        if os.path.isdir(path):
            def loader():
                return cls._dir_loader(path, order_name)
        elif os.path.isfile(path):
            fps = imageio.get_reader(path).get_meta_data().get('fps')

            def loader():
                return cls._file_loader(path)
        else:
            raise Exception("{} is not a valid path".format(path))

        return cls(loader=loader, fps=fps)

    def cook(self, pixels: np.ndarray, i: int = 0) -> np.ndarray:
        return self.recipe(0, 0).cook(self.pierogis[i].pixels)

    def serve(self) -> 'Dish':
        """
        cook the recipe and set the output to this object's pixel array
        """

        cooked_pierogis = []

        for frame in range(self.frames):
            pierogi = self.pierogis[frame]
            # cook with these pixels as first input
            recipe = self.recipe(frame + 1, self.frames)
            cooked_pixels = recipe.cook(pierogi.pixels)
            # ensure that the cooked pixels do not overflow 0-255
            clipped_pixels = np.clip(cooked_pixels, 0, 255)
            # # set the objects own pixels to the result of cooking
            cooked_pierogi = Pierogi(pixels=clipped_pixels)

            cooked_pierogis.append(cooked_pierogi)

        return Dish(pierogis=cooked_pierogis)

    def save(
            self,
            path: str,
            optimize: bool = True,
            duration: float = None,
            fps: float = None
    ) -> None:
        """
        :param duration: ms duration between frames
        """
        if len(self.pierogis) > 1:
            ims = [np.asarray(pierogi.image) for pierogi in self.pierogis]
            if duration is not None:
                fps = 1000 / duration

            if fps is None:
                fps = 30

            imageio.mimwrite(
                path,
                ims=ims,
                fps=fps
            )

            if optimize and os.path.splitext(path)[1] == ".gif":
                try:
                    import pygifsicle
                    pygifsicle.optimize(path)
                except FileNotFoundError as err:
                    print(err)

        elif len(self.pierogis) == 1:
            self.pierogis[0].save(path)

        else:
            raise Exception("Dish has no pierogis")

    def save_frames(
            self,
            frames_dir,
            prefix: str = None
    ) -> List[str]:
        """
        :param frames_dir: directory to save frames into
        :param prefix: add to beginning of each filename separated by '-'
        """
        digits = math.floor(math.log(self.frames, 10)) + 1
        i = 1

        output_filenames = []

        for pierogi in self.pierogis:
            frame_filename = str(i).zfill(digits) + '.png'
            if prefix is not None:
                frame_filename = prefix + '-' + frame_filename

            frame_path = os.path.join(frames_dir, frame_filename)
            threading.Thread(target=pierogi.save, args=(frame_path,)).start()

            output_filenames.append(frame_path)

            i += 1

        return output_filenames
