"""Exercise download failures before a production image can be replaced."""

import hashlib
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("download-deploy-image.sh")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.payload = b"test image archive"
        self.checksum = hashlib.sha256(self.payload).hexdigest()
        self.fixture = self.directory / "fixture.zip"
        self.make_artifact("jobweaver-image.tar.gz")
        bin_dir = self.directory / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text(
            "#!/usr/bin/env python3\n"
            "import os, shutil, sys\n"
            "assert 'test-run-token' not in ' '.join(sys.argv)\n"
            "assert sys.stdin.read() == "
            "'header = \"Authorization: Bearer test-run-token\"\\n'\n"
            "shutil.copyfile(os.environ['ARTIFACT_FIXTURE'], 'image.zip')\n"
            "sys.exit(int(os.environ.get('CURL_EXIT', '0')))\n"
        )
        curl.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "ARTIFACT_FIXTURE": str(self.fixture),
        }

    def make_artifact(self, name):
        with zipfile.ZipFile(self.fixture, "w") as archive:
            archive.writestr(name, self.payload)

    def download(self, checksum=None):
        result = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                str(self.directory),
                "owner/repo",
                "123",
                checksum or self.checksum,
            ],
            input="test-run-token\n",
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )
        self.assertNotIn("test-run-token", result.stdout + result.stderr)
        self.assertFalse((self.directory / "image.zip").exists())
        self.assertFalse((self.directory / "jobweaver-image.tar.gz.part").exists())
        return result

    def test_download_verifies_and_installs_image(self):
        result = self.download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.directory / "jobweaver-image.tar.gz").read_bytes(), self.payload
        )

    def test_bad_checksum_preserves_previous_archive(self):
        image = self.directory / "jobweaver-image.tar.gz"
        image.write_bytes(b"previous archive")
        self.assertNotEqual(self.download("0" * 64).returncode, 0)
        self.assertEqual(image.read_bytes(), b"previous archive")

    def test_unexpected_zip_path_is_rejected(self):
        self.make_artifact("../unexpected-file")
        self.assertNotEqual(self.download().returncode, 0)
        self.assertFalse((self.directory / "jobweaver-image.tar.gz").exists())

    def test_http_failure_does_not_install_image(self):
        self.env["CURL_EXIT"] = "22"
        self.assertNotEqual(self.download().returncode, 0)
        self.assertFalse((self.directory / "jobweaver-image.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()
