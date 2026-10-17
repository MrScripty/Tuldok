"""Current installed runtime alias custody; no migration converter dependency."""
from pathlib import Path
import tempfile
import unittest

import torch_runtime as runtime


class InstalledAliasCustody(unittest.TestCase):
    def test_retargeting_measured_file_alias_is_not_the_same_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed, packages = root / 'python', root / 'packages'
            (installed / 'lib/python3.14').mkdir(parents=True)
            executable = installed / 'bin/python3.14'
            executable.parent.mkdir()
            executable.write_bytes(b'authored nonexecutable runtime fixture')
            for name in ('torch', 'numpy'):
                metadata = packages / (name + '-1.0.dist-info/METADATA')
                metadata.parent.mkdir(parents=True)
                metadata.write_text('Version: 1.0\n')
            first, second = packages / 'first.py', packages / 'second.py'
            first.write_bytes(b'NUMERICAL_MAPPING = 1\n')
            second.write_bytes(b'NUMERICAL_MAPPING = 2\n')
            selected = packages / 'selected.py'
            selected.symlink_to(first.name)
            manifest = runtime.inventory({'python': str(executable),
                'python_root': str(installed), 'site_packages': str(packages)})
            runtime.verify(manifest)
            before = selected.read_bytes()
            selected.unlink()
            selected.symlink_to(second.name)
            self.assertNotEqual(selected.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'topology|symlink|alias|link'):
                runtime.verify(manifest)


if __name__ == '__main__':
    unittest.main()
