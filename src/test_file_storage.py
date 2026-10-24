import os
import uuid
import tempfile
import unittest
from unittest.mock import patch
import file_storage_service as fs

class FileStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(fs, "STORAGE_ROOT", self.temp.name)
        self.root_patch.start()
        self.submission_id = str(uuid.uuid4())
        self.created = []

    def tearDown(self):
        for path in self.created:
            fs.delete_physical_file(path)
        self.root_patch.stop()
        self.temp.cleanup()

    def save(self, name, content):
        result = fs.validate_and_save_file(name, content, self.submission_id)
        if result[0]:
            self.created.append(result[1])
        return result

    def test_valid_utf8_file_and_cleanup(self):
        ok, path, ftype, size, sha, _ = self.save("query.sql", "SELECT 'tiếng Việt';".encode())
        self.assertTrue(ok); self.assertEqual(ftype, "SQL"); self.assertEqual(size, len("SELECT 'tiếng Việt';".encode()))
        self.assertEqual(fs.read_stored_file(path).decode(), "SELECT 'tiếng Việt';")
        self.assertTrue(fs.delete_physical_file(path)); self.created.remove(path)
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, os.path.basename(path))))

    def test_rejects_extension_nul_invalid_utf8_empty_and_size(self):
        self.assertFalse(self.save("bad.exe", b"x")[0])
        self.assertFalse(self.save("nul.txt", b"a\x00b")[0])
        self.assertFalse(self.save("bad.txt", b"\xff")[0])
        self.assertFalse(self.save("empty.txt", b"")[0])
        with patch.object(fs, "MAX_FILE_SIZE_BYTES", 3):
            self.assertFalse(self.save("large.txt", b"four")[0])

    def test_path_traversal_filename_is_replaced(self):
        ok, path, *_ = self.save("../../outside.txt", b"safe text")
        self.assertTrue(ok)
        self.assertEqual(path.split("/")[0], "secure_storage")
        self.assertNotIn("..", path)

    def test_directory_is_created_if_missing(self):
        nested = os.path.join(self.temp.name, "not-created-yet")
        with patch.object(fs, "STORAGE_ROOT", nested):
            result = fs.validate_and_save_file("a.txt", b"ok", self.submission_id)
            self.assertTrue(result[0]); self.assertTrue(os.path.isdir(nested))
            fs.delete_physical_file(result[1])

if __name__ == "__main__":
    unittest.main(verbosity=2)
