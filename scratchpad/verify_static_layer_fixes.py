import os
import shutil
import stat
import tempfile
import logging
import sys

# Configure a basic logger for demonstration purposes
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Mock the necessary parts of StaticLayer for testing
class MockStaticLayer:
    def __init__(self):
        self._temp_dir = None
        self._rules_repo_path = None

    def _handle_remove_read_only(self, func, path, exc_info):
        logger.info(f"[HANDLER] Encountered error on {path} with function {func.__name__}")
        # Check if the error is a PermissionError
        if exc_info[0] is PermissionError:
            try:
                # First, ensure write permission on the item itself
                os.chmod(path, stat.S_IWRITE)
                logger.info(f"[HANDLER] Changed permissions to writable for {path}")

                # If the function was os.unlink (i.e., we're trying to delete a file), retry unlinking it
                if func is os.unlink:
                    func(path) # Explicitly retry unlinking the file
                    logger.info(f"[HANDLER] Successfully retried unlinking file: {path}")
                elif func is os.rmdir:
                    # If it was rmdir, just changing permissions on the directory might be enough
                    # and rmtree will handle the retry/recursion
                    logger.info(f"[HANDLER] Rmdir encountered on {path}. Permissions changed, rmtree will proceed.")
                else:
                    logger.warning(f"[HANDLER] Unhandled function {func.__name__} in onerror for {path}")
                    raise # Re-raise if it's not unlink or rmdir and a permission error

            except Exception as e:
                logger.error(f"[HANDLER] Failed to handle permission error for {path}: {e}")
                raise # Re-raise if changing permissions or retrying fails
        else:
            raise  # Re-raise if not a permission error

    def _cleanup_rules_repo(self) -> None:
        if self._temp_dir and os.path.exists(self._temp_dir):
            temp_dir_to_clean = self._temp_dir # Store in a local variable for rmtree
            logger.info(f"Cleaning up temporary rules directory: {temp_dir_to_clean}")
            try:
                shutil.rmtree(temp_dir_to_clean, onerror=self._handle_remove_read_only)
                logger.info(f"Successfully cleaned up {temp_dir_to_clean}")
            except Exception as e:
                logger.error(f"Error during cleanup of {temp_dir_to_clean}: {e}")
            finally:
                # Only set to None AFTER successful or attempted cleanup
                self._rules_repo_path = None
                self._temp_dir = None
        else:
            logger.info("No temporary directory to clean up or it does not exist.")

    def _detect_language(self, file_path: str) -> str | None:
        extension = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".html": "html",
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".go": "go",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
        }
        return language_map.get(extension)

def test_cleanup_permission_error():
    logger.info("--- Testing _cleanup_rules_repo with PermissionError scenario ---")
    mock_layer = MockStaticLayer()

    # Create a temporary directory and a read-only file inside it
    initial_temp_dir = tempfile.mkdtemp(prefix="test_cleanup_") # Store initial temp dir
    mock_layer._temp_dir = initial_temp_dir

    read_only_file = os.path.join(mock_layer._temp_dir, "test_file.txt")
    with open(read_only_file, "w") as f:
        f.write("This is a test file.")

    # Make the file read-only
    os.chmod(read_only_file, stat.S_IREAD) # Read-only for owner, group, others
    logger.info(f"Created read-only file: {read_only_file}")

    # Attempt to clean up
    try:
        mock_layer._cleanup_rules_repo()
        if not os.path.exists(read_only_file): # Check if the specific file is gone
            logger.info("SUCCESS: Read-only file was successfully removed.")
        else:
            logger.error("FAILURE: Read-only file still exists after cleanup attempt.")

        if not os.path.exists(initial_temp_dir): # Use the stored initial_temp_dir for check
            logger.info("SUCCESS: Temporary directory was cleaned up.")
        else:
            logger.error("FAILURE: Temporary directory still exists after cleanup attempt.")

    except Exception as e:
        logger.error(f"FAILURE: _cleanup_rules_repo raised an unexpected exception: {e}")

def test_detect_language():
    logger.info("--- Testing _detect_language ---")
    mock_layer = MockStaticLayer()

    test_cases = {
        "path/to/file.html": "html",
        "another/file.js": "javascript",
        "yet/another/script.py": "python",
        "config.yaml": "yaml",
        "unknown.xyz": None,
    }

    all_passed = True
    for file_path, expected_language in test_cases.items():
        detected_language = mock_layer._detect_language(file_path)
        if detected_language == expected_language:
            logger.info(f"SUCCESS: {file_path} -> Detected: {detected_language}, Expected: {expected_language}")
        else:
            logger.error(f"FAILURE: {file_path} -> Detected: {detected_language}, Expected: {expected_language}")
            all_passed = False

    if all_passed:
        logger.info("SUCCESS: All _detect_language tests passed.")
    else:
        logger.error("FAILURE: Some _detect_language tests failed.")


if __name__ == "__main__":
    test_cleanup_permission_error()
    print("-" * 50)
    test_detect_language()
