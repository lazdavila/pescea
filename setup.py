"""Setup package"""

from setuptools import setup, find_packages  # type: ignore

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

setup(
    name="python-escea",
    version="1.0.0",
    author="Laz Davila",
    author_email="laz.davila@gmail.com",
    description="A python interface to the Escea fireplace controllers",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    keywords=[
        "Escea",
        "IoT",
    ],
    url="https://github.com/lazdavila/python-pescea",
    python_requires="~=3.8",
    install_requires=["asyncio"],
    tests_require=["pytest"],
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.8",
        "License :: OSI Approved :: " "GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Topic :: Home Automation",
        "Topic :: System :: Hardware",
    ],
)
