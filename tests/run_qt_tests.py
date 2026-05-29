import subprocess
import sys
import os
import time

def run_test(test_file):
    """Run a test file and return the result"""
    print(f"\n{'='*80}")
    print(f"Running test: {test_file}")
    print(f"{'='*80}")

    try:
        # Run the test file as a subprocess
        process = subprocess.Popen([sys.executable, test_file], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True)

        # Wait for the process to complete or timeout after 30 seconds
        start_time = time.time()
        while process.poll() is None and time.time() - start_time < 30:
            time.sleep(0.1)

        # If the process is still running after timeout, kill it
        if process.poll() is None:
            process.terminate()
            print("Test timed out after 30 seconds")
            return False

        # Get the output
        stdout, stderr = process.communicate()

        # Print the output
        print("\nSTDOUT:")
        print(stdout)

        if stderr:
            print("\nSTDERR:")
            print(stderr)

        # Check if the test passed
        if "Error during testing" in stdout or process.returncode != 0:
            print(f"\nTest {test_file} FAILED")
            return False
        else:
            print(f"\nTest {test_file} PASSED")
            return True

    except Exception as e:
        print(f"Error running test {test_file}: {e}")
        return False

def main():
    """Run all Qt tests"""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # List of test files to run
    test_files = [
        os.path.join(script_dir, "test_instanced_vao_qt.py"),
        os.path.join(script_dir, "test_shaders_qt.py"),
        os.path.join(script_dir, "test_vao_shaders_qt.py"),
        os.path.join(script_dir, "test_vao_qt.py")
    ]

    # Run each test
    results = {}
    for test_file in test_files:
        results[test_file] = run_test(test_file)

    # Print summary
    print("\n\n")
    print(f"{'='*80}")
    print("Test Summary")
    print(f"{'='*80}")

    all_passed = True
    for test_file, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"{os.path.basename(test_file)}: {status}")
        if not passed:
            all_passed = False

    # Return exit code
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
