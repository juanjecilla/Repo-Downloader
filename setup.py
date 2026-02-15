from setuptools import setup


setup(
    name="repo-downloader",
    version="0.1.0",
    description="CLI tool for backing up remote repositories.",
    py_modules=["downloader"],
    install_requires=[
        "GitPython",
        "requests",
        "PyYAML",
        "tomli; python_version < '3.11'",
    ],
    entry_points={
        "console_scripts": [
            "repo-downloader=downloader:main",
        ]
    },
)
