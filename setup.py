from setuptools import setup, find_packages

setup(
    name="pyre",
    version="1.5.2",
    author="James Anderson",
    author_email="James.R.Anderson@utah.edu",
    description="A helper library that wraps python threads, multiprocessing, a process pool for shell commands, and parallel python with the same interface",
    long_description=open("README.rst").read(),
    long_description_content_type="text/x-rst",
    url="https://github.com/jamesra/nornir-pyre",
    packages=find_packages(where=".", include=["pyre", "pyre.*"]),
    python_requires=">=3.13",
    install_requires=[
        "dependency-injector >= 4.45.0",
        "six >= 1.16",
        "numpy >= 1.26",
        "matplotlib >= 3.8",
        "rtree>=1.3",
        "PyOpenGL>=3.0",
        "pillow>=2.3",
        "pydantic >= 2.9.2",
        "PyYAML>=6.0.2",
        "wxPython>=4.0",
        "nornir_shared @ git+https://github.com/jamesra/nornir-shared.git@dev-v1.5.2",
        "nornir_pools @ git+https://github.com/jamesra/nornir-pools.git@dev-v1.5.2",
        "nornir_imageregistration @ git+https://github.com/jamesra/nornir-imageregistration.git@cupy-v1.6.5",
        "nornir_buildmanager @ git+https://github.com/jamesra/nornir-buildmanager.git@dev-v1.6.5",
    ],
    extras_require={
        "test": ["nose"],
        "gl": ["pyopengl-accelerate"],
    },
    package_data={
        "pyre": ["resources/*.png"],
    },
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "pyre=pyre.__main__:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
    ],
)
