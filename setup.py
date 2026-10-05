"""Include offline presentation assets in installed wheels and source builds."""
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithAssets(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        for source, name in ((root / "web", "web"), (root / "output/pdf", "pdf")):
            if not source.is_dir():
                raise RuntimeError(f"Required presentation assets missing: {source}")
            self.copy_tree(str(source), str(Path(self.build_lib) / "paritylab/assets" / name))


setup(cmdclass={"build_py": BuildWithAssets})
