import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from gif_similarity_finder.io import collect_gifs, sample_frames


class IoTest(unittest.TestCase):
    def test_collect_gifs_deduplicates_case_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.gif").write_bytes(b"GIF89a")
            (root / "b.GIF").write_bytes(b"GIF89a")

            paths = collect_gifs(root)

            self.assertEqual([path.name for path in paths], ["a.gif", "b.GIF"])

    def test_sample_frames_returns_requested_count_or_less(self) -> None:
        fake_frames = [Image.new("RGB", (8, 8), color=(i, i, i)) for i in range(5)]

        with mock.patch("gif_similarity_finder.io.Image.open"), mock.patch(
            "gif_similarity_finder.io.ImageSequence.Iterator",
            return_value=fake_frames,
        ):
            frames = sample_frames(Path("demo.gif"), n_frames=3)

        self.assertEqual(len(frames), 3)


if __name__ == "__main__":
    unittest.main()
