"""Setup package"""

from distutils.core import setup

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()


setup(
    name="pescea",
    packages=["pescea"],
    version="1.0.2",
    license="gpl-3.0",
    description="Python Escea Fireplace Interface",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="Laz Davila",
    author_email="laz.davila@gmail.com",
    url="https://github.com/lazdavila/pescea",
    download_url="https://github.com/lazdavila/pescea/archive/refs/tags/v1.0.2.tar.gz",
    keywords=[
        "Escea",
        "IoT",
    ],
    install_requires=[
        "asyncio",
        "async_timeout",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Home Automation",
        "Topic :: System :: Hardware",
        "License :: OSI Approved :: " "GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
