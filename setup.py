import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="alexandria-lavedonio",
    version="0.0.4",
    author="Daniel Lavedonio de Lima",
    author_email="daniel.lavedonio@gmail.com",
    description="A package to help with DB connections and commonly used functionally in data analytics",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Lavedonio/alexandria",
    packages=setuptools.find_packages(),
    install_requires=[
        'pyyaml',
        'boto3',
        'google-cloud-bigquery',
        'google-cloud-storage',
        'pandas',
        'psycopg2',
    ],
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    platforms=['any'],
)
